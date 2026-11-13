"""물리 볼륨별 예상 증가량과 조회 실패의 차단 시험."""
from core.resource_budget import plan_resources, volume_info


def test_real_volume_lookup_for_existing_and_planned_paths(tmp_path):
    existing = volume_info(tmp_path)
    planned = volume_info(tmp_path / "not-yet-created" / "nested")
    assert existing["id"] == planned["id"]
    assert isinstance(planned["free"], int)
    assert planned["free"] >= 0


def test_same_volume_aggregates_backup_generation_and_headroom(tmp_path):
    source = tmp_path / "data"
    source.mkdir()
    (source / "a").write_bytes(b"12345")
    probe = lambda path: {"id": "disk", "free": 24}
    result = plan_resources({"data": source}, tmp_path / "backup", {source: 10}, 10,
                            volume_probe=probe, memory_available_bytes=3 * 1024 ** 3)
    assert result["blocked"]
    assert result["volumes"][0]["required"] == 25
    result = plan_resources({"data": source}, tmp_path / "backup", {source: 10}, 10,
                            volume_probe=lambda p: {"id": "disk", "free": 25},
                            memory_available_bytes=3 * 1024 ** 3)
    assert not result["blocked"]


def test_separate_volumes_and_unknown_budgets(tmp_path):
    source = tmp_path / "data"
    source.mkdir()
    (source / "a").write_bytes(b"12345")
    backup = tmp_path / "backup"
    probe = lambda p: {"id": "backup" if p == backup else "data", "free": 30}
    result = plan_resources({"data": source}, backup, {source: 10}, 10,
                            volume_probe=probe, memory_available_bytes=3 * 1024 ** 3)
    assert sorted(v["required"] for v in result["volumes"]) == [5, 20]
    for reserves, headroom in (({source: None}, 10), ({source: 10}, None), ({}, 10)):
        assert plan_resources({"data": source}, backup, reserves, headroom,
                              volume_probe=probe, memory_available_bytes=3 * 1024 ** 3)["blocked"]


def test_memory_thresholds_and_volume_probe_failure(tmp_path):
    source = tmp_path / "data"
    source.mkdir()
    kwargs = dict(roots={"data": source}, backup_dir=tmp_path / "backup",
                  generation_reserves={source: 0}, product_headroom_bytes=0)
    probe = lambda p: {"id": "disk", "free": 0}
    for avail, level in ((None, "BLOCK"), (1024 ** 3 - 1, "BLOCK"),
                         (1024 ** 3, "WARN"), (2 * 1024 ** 3, "OK")):
        result = plan_resources(**kwargs, volume_probe=probe, memory_available_bytes=avail)
        assert next(i for i in result["items"] if i["key"] == "memory")["level"] == level
    assert plan_resources(**kwargs, volume_probe=lambda p: None,
                          memory_available_bytes=3 * 1024 ** 3)["blocked"]


def test_additional_workspace_reserve_is_charged(tmp_path):
    source = tmp_path / "data"
    source.mkdir()
    result = plan_resources({"data": source}, tmp_path / "backup",
                            {source: 10, tmp_path / "work": 50}, 10,
                            volume_probe=lambda p: {"id": "same", "free": 69},
                            memory_available_bytes=3 * 1024 ** 3)
    assert result["blocked"]
    assert result["volumes"][0]["required"] == 70


def test_restore_budget_includes_retained_live_data_and_archive(tmp_path):
    source = tmp_path / "data"
    source.mkdir()
    (source / "a").write_bytes(b"12345")
    result = plan_resources({"data": source}, tmp_path / "backup", {source: 10}, 0,
                            restore_after=True,
                            volume_probe=lambda p: {"id": "same", "free": 34},
                            memory_available_bytes=3 * 1024 ** 3)
    assert result["blocked"]
    assert result["volumes"][0]["required"] == 35  # backup5+generation10+restore5+archive15
def test_capacity_estimate_does_not_read_image_contents(tmp_path, monkeypatch):
    from pathlib import Path
    from core.resource_budget import plan_resources, GIB
    root = tmp_path / 'images'
    root.mkdir()
    (root / 'large.img').write_bytes(b'fixture')
    def deny_content(*a, **k):
        raise AssertionError('capacity estimation must use metadata, not image bytes')
    monkeypatch.setattr(Path, 'open', deny_content)
    result = plan_resources({'images': root}, tmp_path / 'backup', {root: 100}, 0,
                            volume_probe=lambda path: {'id': 'same', 'free': 4 * GIB},
                            memory_available_bytes=4 * GIB)
    assert result['blocked'] is False
    assert result['volumes'][0]['required'] == 107


def test_incremental_restore_reserves_largest_file_per_volume_not_full_trees(tmp_path, monkeypatch):
    from pathlib import Path
    roots = {name: tmp_path / name for name in ('images', 'exports')}
    for root in roots.values():
        root.mkdir()
        (root / 'a').write_bytes(b'12345')
        (root / 'b').write_bytes(b'123')
    backup = tmp_path / 'nas'
    def deny_content(*a, **k):
        raise AssertionError('capacity estimation must read metadata only')
    monkeypatch.setattr(Path, 'open', deny_content)
    result = plan_resources(roots, backup, {p: 2 for p in roots.values()}, 10,
                            incremental_restore=True, restore_after=True, db_backup_bytes=3,
                            volume_probe=lambda p: {'id': 'nas' if p == backup else 'local', 'free': 100},
                            memory_available_bytes=3 * 1024 ** 3)
    assert not result['blocked']
    assert {v['id']: v['required'] for v in result['volumes']} == {'nas': 42, 'local': 19}


def test_headroom_uses_maximum_once_for_shared_product_and_usb_volume(tmp_path):
    product, usb = tmp_path / 'data', tmp_path / 'usb'
    product.mkdir()
    usb.mkdir()
    result = plan_resources({'usb': usb, 'product': product}, tmp_path / 'nas',
                            {product: 0, usb: 0}, 10, root_headroom_bytes={usb: 2},
                            volume_probe=lambda p: {'id': 'same', 'free': 10},
                            memory_available_bytes=3 * 1024 ** 3)
    assert not result['blocked']
    assert result['volumes'][0]['required'] == 10


def test_unc_volume_identity_and_available_space_use_windows_share_api(monkeypatch):
    import ctypes
    import os
    import pytest
    if os.name != 'nt':
        pytest.skip('Windows API contract')
    import core.resource_budget as module
    calls = []
    def disk_free(path, available, total, free):
        calls.append(path)
        available._obj.value = 123
        return 1
    kernel = type('Kernel', (), {})()
    kernel.GetDiskFreeSpaceExW = disk_free
    monkeypatch.setattr(ctypes, 'WinDLL', lambda *a, **k: kernel)
    monkeypatch.setattr(module, '_check_path', lambda path: module.Path(path))
    monkeypatch.setattr(module.Path, 'exists', lambda path: (_ for _ in ()).throw(AssertionError('no network stat')))
    first = volume_info(r'\\Server\Share\folder')
    second = volume_info(r'\\?\UNC\server\share\another')
    assert first == second == {'id': r'unc:\\server\share', 'free': 123}
    assert len(calls) == 2


def test_unc_free_space_query_failure_blocks_without_local_fallback(tmp_path, monkeypatch):
    import ctypes
    import os
    import pytest
    import core.resource_budget as module
    if os.name != 'nt':
        pytest.skip('Windows API contract')
    class Function:
        def __call__(self, *args): return 0
    kernel = type('Kernel', (), {'GetDiskFreeSpaceExW': Function()})()
    monkeypatch.setattr(ctypes, 'WinDLL', lambda *a, **k: kernel)
    root = tmp_path / 'data'
    root.mkdir()
    result = plan_resources({'data': root}, r'\\Server\Share\missing', {root: 0}, 0,
                            incremental_restore=True, memory_available_bytes=3 * 1024 ** 3)
    assert result['blocked']
    assert result['volumes'] == []


def test_shared_preservation_reserves_after_database_without_restoring(tmp_path):
    root, backup = tmp_path / 'data', tmp_path / 'nas'
    root.mkdir()
    (root / 'file').write_bytes(b'12345')
    result = plan_resources({'data': root}, backup, {root: 2}, 0,
                            incremental_restore=True, restore_after=False, db_backup_bytes=3,
                            volume_probe=lambda p: {'id': 'nas' if p == backup else 'local', 'free': 100},
                            memory_available_bytes=3 * 1024 ** 3)
    assert not result['blocked']
    assert {v['id']: v['required'] for v in result['volumes']} == {'nas': 18, 'local': 2}

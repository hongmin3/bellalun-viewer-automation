"""회수 원본을 유지하면서 수집 범위 안의 증거 링크만 상대경로로 파생한다."""
import hashlib
import html
import json
import ntpath
from pathlib import Path
import posixpath
from urllib.parse import unquote, urlsplit

from bellalunauto.share import _ATTR, _CSS
from remote.bundles import check_local


def derive_views(output, remote_workspace):
    output = Path(output)
    reports = output / "workspace" / "Reports"
    if not reports.is_dir():
        return []
    originals = {}
    remote_workspace = ntpath.normpath(remote_workspace)
    for folder in ("Reports", "Evidence"):
        root = output / "workspace" / folder
        for source in root.rglob("*") if root.exists() else []:
            check_local(source)
            if source.is_file():
                relative = source.relative_to(output / "workspace").as_posix()
                remote = ntpath.normcase(ntpath.join(remote_workspace, relative.replace("/", "\\")))
                originals[remote] = (source, relative)
    derivations = []
    for remote, (source, relative) in originals.items():
        content = source.read_bytes()
        def link(reference):
            if reference.startswith("#"):
                return reference
            reference = html.unescape(reference)
            parsed = urlsplit(reference)
            if parsed.scheme == "file":
                if parsed.netloc:
                    return None
                reference = unquote(parsed.path).lstrip("/")
            elif parsed.scheme and len(parsed.scheme) != 1:
                return None
            else:
                reference = unquote(reference.split("#", 1)[0].split("?", 1)[0])
            target = ntpath.normcase(ntpath.normpath(reference if ntpath.isabs(reference)
                                                    else ntpath.join(ntpath.dirname(remote), reference)))
            if target not in originals:
                return None
            return posixpath.relpath(originals[target][1], posixpath.dirname(relative))
        if relative.startswith("Reports/") and source.suffix.lower() == ".json":
            value = json.loads(content.decode("utf-8-sig"))
            def rewrite(value, reference=False):
                if isinstance(value, dict):
                    return {key: rewrite(child, reference or key in {"evidence", "logs", "dicom"}) for key, child in value.items()}
                if isinstance(value, list):
                    return [rewrite(child, reference) for child in value]
                if reference and isinstance(value, str):
                    return link(value) or "[수집 범위 밖 또는 없는 증거]"
                return value
            content = json.dumps(rewrite(value), ensure_ascii=False, indent=2).encode()
        elif relative.startswith("Reports/") and source.suffix.lower() == ".html":
            text = content.decode("utf-8-sig")
            text = _ATTR.sub(lambda match: match[1] + '="' + html.escape(link(match[3] or match[4]) or "#unavailable", quote=True) + '"', text)
            text = _CSS.sub(lambda match: 'url("' + (link(match[2] or match[3]) or "#unavailable") + '")', text)
            content = text.encode()
        target = check_local(output / "view" / relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        derivations.append({"source": source.relative_to(output).as_posix(),
                            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                            "derived": target.relative_to(output).as_posix(),
                            "derived_sha256": hashlib.sha256(content).hexdigest()})
    (output / "view-derivations.json").write_text(json.dumps(derivations, indent=2), encoding="utf-8")
    return derivations

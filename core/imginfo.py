# -*- coding: utf-8 -*-
r"""Bellalun `.img` 파일 끝에 붙은 `<INFORMATION>` XML 을 읽는다.

## 왜 필요한가

사양서1 `SRS 03-50-230`(Post Reconstruction)은 3D 영상 처리 값의 저장 위치를
**img 파일**로 못박는다.

    "Apply 를 누르게 되면 해당 img 파일에 영상 조정 파라미터 값들이 저장된다"
    "img 에 해당 옵션 설정 값을 저장한다. (Recon/Syn Background Masking: 1/0, BOOL)"

그리고 같은 문서의 개발 사양은 그 항목 이름까지 적어 둔다 —
`ReconParam` 의 `EgpName, EapName, XtpName, PostBackgroundMasking, PostContrast, ...`.

**DB 에는 이 정보가 없다.** `DATA` 데이터베이스 전체에서 파라미터 이름을 담은
열은 하나도 없다(2026-08-24 `INFORMATION_SCHEMA` 전수 조회로 확인). 즉 "이 3D
영상에 실제로 어떤 Recon Parameter 가 적용됐는가"는 **화면 OCR 아니면 이
파일뿐**이고, 화면보다 파일이 훨씬 강한 증거다.

## 파일 구조 (2026-08-24 실측, Bellalun 1.0.12.105)

`.img` 는 `..BELLALUN.IMG.` 매직으로 시작하는 이진 컨테이너이고, **끝부분에
UTF-16LE 로 인코딩된 XML 한 덩어리**가 들어 있다.

    <?xml version="1.0"?>
    <INFORMATION>
      <PATIENT_INFO>...<STUDY_INFO>...<SERIES_INFO>...
      <INSTANCE_GROUP_INFO>
        <InstanceGroup Key=".." ExposureType="1" ExposureMode="1" .../>
        <ViewPosition Name="CC" Type="1" Laterality="1" .../>
        <ReconParam EgpName="narrow_standard.egp" EapName="common_standard.eap"
                    XtpName="TEST_3D_FLOW.xtp" PostContrast="14" .../>
        <RawInfo RawInstanceUID=".."/>
      </INSTANCE_GROUP_INFO>
      <DOSE_LIST>...<DEVICE_INFO>...<INSTANCE_INFO>...<FRAME_LIST>...
      <ANNOTATION_INFO>...
    </INFORMATION>

실측으로 확인한 것

  - 2D 영상(`ViewPosition/@Type=0`)도 `ReconParam` 을 가지지만 이름 3개
    (`EgpName`/`EapName`/`XtpName`)가 **모두 빈 문자열**이다. 그래서 이 모듈은
    3D 파라미터 판정에만 쓴다. 2D 의 `.pim` 이름은 img 에 없다.
  - `EgpName` 은 촬영 모드를 따라간다. **2026-08-24 에 두 모드를 실제로 촬영해
    확정했다** — 3D-Narrow(`ExposureMode=1`) = `narrow_standard.egp`,
    3D-Wide(`ExposureMode=2`) = `wide_standard.egp`.
    `C:\XIPL\PARAMETER` 에 설치된 `.egp` 도 그 두 개뿐이다.
    그래도 판정은 특정 파일명을 기대값으로 박지 않고 **"두 모드의 EgpName 이 서로
    다르다"** 까지만 한다(`tests/xipl_flows.compatibility_07` Step 8) — 제품이
    파일명을 바꿔도 모드 분리라는 사양(`SRS 03-10-110`)은 그대로 검증된다.
  - **`ViewPosition/@Type` 도 촬영 모드를 구분해 기록한다** — 3D-N 은 `1`,
    3D-W 는 `2`(2026-08-24 실측). `VIEW_POSITION_PRESET.Type` 과 같은 체계다.
    (그전에는 "3D 면 1" 로만 알고 있었다.)
  - `ExposureMode` 는 `INSTANCE_GROUP.ExposureMode` 와 같은 값이다
    (1=Narrow / 2=Wide, `tests/system_compat.py` 에서 대조 확정).
  - `XtpName` 은 **Preset 에 등록된 View Position 을 촬영하면 그 Preset 의 값**이
    들어간다(실측: 두 모드 모두 `DBT_Standard_Default.xtp`). 사양서1 185~186쪽
    SRS 03-10-110 의 "Preset 으로 등록되어 있는 경우 해당 Viewposition 에 설정해
    놓은 파라미터로 처리한다" 와 일치한다 — `Setting > Procedure > General` 의
    Default 를 바꿔도 Preset 등록 위치에는 반영되지 않는다.

## 읽는 방법

XML 은 파일 끝에 있으므로 **꼬리만 읽는다.** 3D Raw 는 700MB 를 넘어(실측
710,001,874 바이트) 전체를 읽으면 회귀가 그것만으로 수십 초를 쓴다.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET

#: UTF-16LE 로 인코딩된 XML 시작/끝 표식.
_XML_HEAD = "<?xml".encode("utf-16-le")
_XML_TAIL = "</INFORMATION>".encode("utf-16-le")

#: 꼬리에서 읽을 기본 크기. 실측 최대 XML 길이는 약 29KB(3D Recon)이므로
#: 4MB 면 충분히 여유롭고, 700MB 파일에서도 한 번의 seek+read 로 끝난다.
DEFAULT_TAIL_BYTES = 4 * 1024 * 1024


class ImgInfoError(RuntimeError):
    pass


def read_information(path, tail_bytes=DEFAULT_TAIL_BYTES):
    """`.img` 꼬리의 `<INFORMATION>` XML 문자열을 돌려준다.

    찾지 못하면 `ImgInfoError`. 조용히 `None` 을 돌려주지 않는다 — 판정 코드가
    "정보가 없다"와 "형식이 바뀌었다"를 구분하지 못하면 결함을 놓친다.
    """
    if not os.path.isfile(path):
        raise ImgInfoError(f"img 파일이 없습니다: {path}")
    size = os.path.getsize(path)
    with open(path, "rb") as stream:
        stream.seek(max(0, size - tail_bytes))
        blob = stream.read()
    start = blob.rfind(_XML_HEAD)
    if start < 0:
        raise ImgInfoError(
            f"꼬리 {min(size, tail_bytes)}바이트에서 UTF-16LE XML 시작을 찾지 "
            f"못했습니다: {path}")
    end = blob.find(_XML_TAIL, start)
    if end < 0:
        raise ImgInfoError(f"</INFORMATION> 닫는 태그를 찾지 못했습니다: {path}")
    return blob[start:end + len(_XML_TAIL)].decode("utf-16-le", "replace")


def sections(path, tail_bytes=DEFAULT_TAIL_BYTES):
    """자주 쓰는 요소를 `{이름: 속성 dict}` 로 뽑아 준다.

    없는 요소는 키 자체가 빠진다(빈 dict 로 채우면 "속성이 비었다"와 구분이
    안 된다).
    """
    root = ET.fromstring(read_information(path, tail_bytes))
    wanted = {
        "patient": "PATIENT_INFO/Patient",
        "study": "STUDY_INFO/Study",
        "series": "SERIES_INFO/Series",
        "instance_group": "INSTANCE_GROUP_INFO/InstanceGroup",
        "view_position": "INSTANCE_GROUP_INFO/ViewPosition",
        "recon_param": "INSTANCE_GROUP_INFO/ReconParam",
        "instance": "INSTANCE_INFO/Instance",
    }
    out = {}
    for name, xpath in wanted.items():
        element = root.find(xpath)
        if element is not None:
            out[name] = dict(element.attrib)
    return out


def recon_param(path, tail_bytes=DEFAULT_TAIL_BYTES):
    """`<ReconParam>` 속성. 없으면 `ImgInfoError`."""
    found = sections(path, tail_bytes).get("recon_param")
    if found is None:
        raise ImgInfoError(f"<ReconParam> 요소가 없습니다: {path}")
    return found


def study_image_dirs(data_dir, study_key):
    """한 검사의 영상 폴더들. 같은 Study Key 로 폴더가 여러 개 생긴다.

    실측: `C:\\BellalunData\\Image\\Study48_20260821_145346` 처럼
    `Study<Key>_<날짜>_<시각>` 이고, 같은 검사를 다시 열면 새 폴더가 생긴다.
    그래서 최신 것부터 훑어야 방금 촬영한 영상을 찾는다.
    """
    root = os.path.join(data_dir, "Image")
    if not os.path.isdir(root):
        return []
    prefix = f"Study{int(study_key)}_"
    found = [os.path.join(root, name) for name in os.listdir(root)
             if name.startswith(prefix)
             and os.path.isdir(os.path.join(root, name))]
    return sorted(found, reverse=True)


def instance_image_path(data_dir, study_key, instance_key):
    """`INSTANCE.[Key]` 에 해당하는 `.img` 경로. 없으면 `None`."""
    target = f"Image{int(instance_key)}.img"
    for folder in study_image_dirs(data_dir, study_key):
        candidate = os.path.join(folder, target)
        if os.path.isfile(candidate):
            return candidate
    return None

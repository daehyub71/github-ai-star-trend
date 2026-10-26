"""테스트 하네스 — 규칙을 사람 대신 코드가 지키게 한다 (SPEC NFR-14).

- 네트워크 차단: conftest 의 autouse 픽스처가 쓴다 (`live` 표시 테스트만 예외).
- 층 규칙 검사기: test_architecture 가 쓴다. 검사기 자체가 위반을 잡는지 통제군 테스트로 확인한다.
"""

import ast
from collections.abc import Mapping
from pathlib import Path

PACKAGE = "startrend"

# 층마다 import 해도 되는 startrend 층 (PLAN 1-2: 위가 아래를 쓴다, 순환 없음)
ALLOWED: dict[str, set[str]] = {
    "core": {"core"},
    "clients": {"core", "clients"},
    "gate": {"core", "clients", "gate"},
    "stages": {"core", "clients", "gate", "stages"},  # stages 끼리는 아래에서 따로 막는다
    "cli": {"core", "clients", "gate", "stages", "cli"},
    "package": set(),
}
# 네트워크에 직접 닿는 표준 라이브러리 모듈. clients 의 전송 계층에서만 쓴다
NETWORK_MODULES = {"socket", "ssl", "http.client", "urllib.request", "ftplib", "smtplib"}
NETWORK_ALLOWED_FILES = {"startrend/clients/transport.py"}


class NetworkBlocked(RuntimeError):
    """기본 테스트 게이트에서 네트워크에 접속하려 했다 (NFR-1·NFR-14)."""


def layer_of(relpath: str) -> str:
    parts = relpath.split("/")
    if parts == ["startrend", "__init__.py"]:
        return "package"
    if parts == ["startrend", "__main__.py"]:
        return "cli"
    if len(parts) == 2 and parts[1] in ("gate.py", "budget.py"):
        return "gate"
    if parts[1] in ("core", "clients", "stages"):
        return parts[1]
    raise ValueError(f"층을 알 수 없는 모듈: {relpath}")


def _imports(tree: ast.AST) -> list[tuple[int, str, list[str]]]:
    """(줄, 모듈, from-import 이름들). 상대 import 는 모듈 이름 앞에 '.' 를 남긴다."""
    out: list[tuple[int, str, list[str]]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.append((node.lineno, a.name, []))
        elif isinstance(node, ast.ImportFrom):
            mod = "." * node.level + (node.module or "")
            out.append((node.lineno, mod, [a.name for a in node.names]))
    return out


def check_sources(sources: Mapping[str, str]) -> list[str]:
    """{상대경로: 소스} → 위반 목록. 비어 있으면 통과."""
    violations: list[str] = []
    for relpath, src in sorted(sources.items()):
        layer = layer_of(relpath)
        own_stage = Path(relpath).stem if layer == "stages" else None
        for lineno, mod, names in _imports(ast.parse(src, filename=relpath)):
            where = f"{relpath}:{lineno}"
            if mod.startswith("."):
                violations.append(f"{where} 상대 import 금지 — 절대 경로로 쓴다 ({mod})")
                continue
            # 네트워크 모듈
            full = {mod} | {f"{mod}.{n}" for n in names}
            if full & NETWORK_MODULES and relpath not in NETWORK_ALLOWED_FILES:
                violations.append(f"{where} 네트워크 모듈은 clients/transport.py 에서만 ({mod})")
            # 층 규칙
            if mod != PACKAGE and not mod.startswith(PACKAGE + "."):
                continue
            target = mod.split(".")[1] if "." in mod else ""
            target_layer = {"gate": "gate", "budget": "gate", "__main__": "cli"}.get(target, target)
            if target_layer and target_layer not in ALLOWED[layer]:
                violations.append(f"{where} {layer} 층은 {target_layer} 층을 import 할 수 없다 ({mod})")
            # 단계끼리 import 금지
            if layer == "stages" and target == "stages":
                others = [n for n in names] if mod == f"{PACKAGE}.stages" else [mod.split(".")[2]]
                for other in others:
                    if other != own_stage:
                        violations.append(f"{where} 단계끼리 import 금지 — 앞 단계의 파일만 읽는다 ({other})")
    return violations


def project_sources(root: Path) -> dict[str, str]:
    pkg = root / PACKAGE
    return {
        f.relative_to(root).as_posix(): f.read_text(encoding="utf-8")
        for f in sorted(pkg.rglob("*.py"))
        if "__pycache__" not in f.parts
    }

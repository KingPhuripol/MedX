import ast
import re

from .conftest import REPO_ROOT
from .repo_files import read_text, repo_files

FORBIDDEN_SDKS = {
    "openai", "anthropic", "google.generativeai", "google.genai", "vertexai", "cohere", "mistralai",
    "groq", "together", "litellm", "langchain", "langchain_openai", "langchain_anthropic", "boto3",
}
ADAPTERS_NEEDLE = ".".join(["gateway", "adapters"])  # built so this file does not self-match
GATEWAY_DIR = REPO_ROOT / "backend" / "app" / "gateway"
WEB_DIR = REPO_ROOT / "web"
WEB_PROVIDER_TERMS = re.compile(
    r"openai|anthropic|gemini|mistral|cohere|MockProvider|OpenAICompatible|openai_compatible|adapter",
    re.IGNORECASE,
)
SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]{10,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(r"\bghp_[A-Za-z0-9]{36}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bhf_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
]
CODE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".json", ".toml", ".yml", ".yaml", ".lock", ".in"}
CLAIM_TERMS = re.compile(r"diagnos|prescrib|treat", re.IGNORECASE)
DISCLAIMER_EN = (
    "Research prototype — not for clinical use. Outputs are suggestions for review and "
    "require confirmation by a clinician."
)
DISCLAIMER_TH = "ต้นแบบเพื่อการวิจัย ไม่ใช้กับผู้ป่วยจริง ผลลัพธ์เป็นข้อเสนอที่ต้องให้บุคลากรยืนยัน"


def _imported_modules(tree: ast.AST) -> set[str]:
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
    return mods


def test_provider_isolation():
    files = repo_files(REPO_ROOT)
    py_files = [p for p in files if p.suffix == ".py"]
    assert py_files, "scan found no python files"
    violations: list[str] = []
    for path in py_files:
        mods = _imported_modules(ast.parse(path.read_text(encoding="utf-8")))
        for mod in mods:
            if any(mod == sdk or mod.startswith(sdk + ".") for sdk in FORBIDDEN_SDKS):
                violations.append(f"{path}: imports provider SDK {mod}")
    # Lockfiles must not pull in provider SDKs either.
    lock = read_text(REPO_ROOT / "requirements.lock") or ""
    for sdk in FORBIDDEN_SDKS:
        if re.search(rf"^{re.escape(sdk)}==", lock, re.MULTILINE):
            violations.append(f"requirements.lock pins provider SDK {sdk}")
    # Adapters are private to the gateway package (code and config files; prose docs excluded).
    for path in files:
        if GATEWAY_DIR in path.parents or path.suffix not in CODE_SUFFIXES and path.name != "Makefile":
            continue
        text = read_text(path)
        if text and ADAPTERS_NEEDLE in text:
            violations.append(f"{path}: references adapters outside the gateway")
    # The web client knows nothing about providers or adapters.
    for path in files:
        if WEB_DIR in path.parents and path.name != "package-lock.json":
            text = read_text(path)
            if text and (m := WEB_PROVIDER_TERMS.search(text)):
                violations.append(f"{path}: provider/adapter term {m.group(0)!r} in web client")
    assert violations == []


def test_repo_hygiene():
    gitignore = (REPO_ROOT / ".gitignore").read_text().splitlines()
    assert ".env" in gitignore and "!.env.example" in gitignore
    assert "*.db" in gitignore
    files = repo_files(REPO_ROOT)
    rel = {p.relative_to(REPO_ROOT).as_posix() for p in files}
    assert ".env.example" in rel
    assert not [r for r in rel if r.split("/")[-1].startswith(".env") and r.split("/")[-1] != ".env.example"]
    assert not [r for r in rel if r.endswith(".db")]

    leaks = []
    for path in files:
        text = read_text(path)
        if text is None:
            continue
        for pat in SECRET_PATTERNS:
            if pat.search(text):
                leaks.append(f"{path}: matches {pat.pattern}")
    assert leaks == []

    # The external key is read from the environment only.
    assert "EXTERNAL_API_KEY=" in (REPO_ROOT / ".env.example").read_text()
    env_example_key = [
        line for line in (REPO_ROOT / ".env.example").read_text().splitlines() if line.startswith("EXTERNAL_API_KEY=")
    ]
    assert env_example_key == ["EXTERNAL_API_KEY="]

    claims = []
    ui_files = [p for p in files if p.suffix in {".ts", ".tsx"} and (WEB_DIR / "app") in p.parents]
    ui_files += [p for p in files if p.suffix in {".ts", ".tsx"} and (WEB_DIR / "components") in p.parents]
    assert ui_files, "no web UI files scanned"
    for path in ui_files:
        text = (read_text(path) or "").replace(DISCLAIMER_EN, "").replace(DISCLAIMER_TH, "")
        if m := CLAIM_TERMS.search(text):
            claims.append(f"{path}: {m.group(0)!r}")
    assert claims == []

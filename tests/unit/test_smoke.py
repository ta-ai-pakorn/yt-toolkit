import yttoolkit


def test_version_is_set():
    assert yttoolkit.__version__ == "0.1.0"


def test_sources_compile_without_warnings():
    # SyntaxWarning (เช่น backslash ใน docstring) โผล่แค่ตอน compile ครั้งแรก จึงต้อง compile เองทุกไฟล์
    import warnings
    from pathlib import Path

    root = Path(yttoolkit.__file__).parent
    for source in sorted(root.rglob("*.py")):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            compile(source.read_text(encoding="utf-8"), str(source), "exec")

"""주식 분석 모듈."""
# Streamlit Cloud venv에서 setuptools 누락 시 자동 복구
# pykrx가 import pkg_resources를 하는데 일부 환경에서 setuptools 없음
import sys

if "pkg_resources" not in sys.modules:
    try:
        import pkg_resources  # noqa: F401
    except ImportError:
        try:
            import subprocess
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--quiet", "setuptools"]
            )
            import pkg_resources  # noqa: F401
        except Exception:
            pass

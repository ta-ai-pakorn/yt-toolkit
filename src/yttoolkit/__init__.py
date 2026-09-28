"""YT Toolkit: เครื่องมือจัดการสื่อจากยูทูปที่รันบนเครื่องผู้ใช้"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("yttoolkit")
except PackageNotFoundError:  # รันจาก source ที่ยังไม่ติดตั้ง
    __version__ = "0.0.0"

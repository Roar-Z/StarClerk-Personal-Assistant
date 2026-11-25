"""PyInstaller 用的入口，绕开相对导入，别删。"""
from installer.main import main

raise SystemExit(main())

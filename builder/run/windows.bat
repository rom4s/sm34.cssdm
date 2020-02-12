@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\2017\BuildTools\VC\Auxiliary\Build\vcvarsall.bat" x86
SET SELF_PATH=%~dp0%
echo BUILDER_PATH = %SELF_PATH%

SET CXX=
SET CC=
SET HOME=C:\Users\%USERNAME%

cd cssdm && python %SELF_PATH:~0,-1%\build.py --mms-path %HOME%\mmsource\ --sm-path %HOME%\sourcemod\ --sm-bin-path %HOME%\sourcemod-bin\ --hl2sdk-ep1 %HOME%\hl2sdk-episode1\
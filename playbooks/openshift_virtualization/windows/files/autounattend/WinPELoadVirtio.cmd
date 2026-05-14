@echo off
setlocal EnableExtensions
REM WinPE: load viostor from quay.io/kubevirt/virtio-container-disk (amd64\<release>\) or virtio-win.iso (viostor\...\amd64\).
set "PNPUTIL=%SystemRoot%\System32\pnputil.exe"
if not exist "%PNPUTIL%" set "PNPUTIL=pnputil.exe"

for %%L in (D E F G H I J K L M N O P Q R S T U V W) do if exist "%%L:\drivers\amd64\2k22\viostor.inf" (
  "%PNPUTIL%" /add-driver "%%L:\drivers\amd64\2k22\*.inf" /install /subdirs
  exit /b %ERRORLEVEL%
)
for %%L in (D E F G H I J K L M N O P Q R S T U V W) do if exist "%%L:\amd64\2k22\viostor.inf" (
  "%PNPUTIL%" /add-driver "%%L:\amd64\2k22\*.inf" /install /subdirs
  exit /b %ERRORLEVEL%
)
for %%L in (D E F G H I J K L M N O P Q R S T U V W) do if exist "%%L:\amd64\w11\viostor.inf" (
  "%PNPUTIL%" /add-driver "%%L:\amd64\w11\*.inf" /install /subdirs
  exit /b %ERRORLEVEL%
)
for %%L in (D E F G H I J K L M N O P Q R S T U V W) do if exist "%%L:\amd64\w10\viostor.inf" (
  "%PNPUTIL%" /add-driver "%%L:\amd64\w10\*.inf" /install /subdirs
  exit /b %ERRORLEVEL%
)
for %%L in (D E F G H I J K L M N O P Q R S T U V W) do if exist "%%L:\amd64\2k19\viostor.inf" (
  "%PNPUTIL%" /add-driver "%%L:\amd64\2k19\*.inf" /install /subdirs
  exit /b %ERRORLEVEL%
)
for %%L in (D E F G H I J K L M N O P Q R S T U V W) do if exist "%%L:\viostor\w11\amd64\viostor.inf" (
  "%PNPUTIL%" /add-driver "%%L:\viostor\w11\amd64\viostor.inf" /install
  exit /b %ERRORLEVEL%
)
for %%L in (D E F G H I J K L M N O P Q R S T U V W) do if exist "%%L:\viostor\2k22\amd64\viostor.inf" (
  "%PNPUTIL%" /add-driver "%%L:\viostor\2k22\amd64\viostor.inf" /install
  exit /b %ERRORLEVEL%
)
for %%L in (D E F G H I J K L M N O P Q R S T U V W) do if exist "%%L:\viostor\w10\amd64\viostor.inf" (
  "%PNPUTIL%" /add-driver "%%L:\viostor\w10\amd64\viostor.inf" /install
  exit /b %ERRORLEVEL%
)

exit /b 1

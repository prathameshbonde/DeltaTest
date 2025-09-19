@ECHO OFF
SETLOCAL ENABLEDELAYEDEXPANSION

set DIR=%~dp0
set WRAPPER_DIR=%DIR%gradle\wrapper
set WRAPPER_JAR=%WRAPPER_DIR%\gradle-wrapper.jar
set PROPS=%WRAPPER_DIR%\gradle-wrapper.properties

IF NOT EXIST "%WRAPPER_DIR%" mkdir "%WRAPPER_DIR%"

IF NOT EXIST "%WRAPPER_JAR%" (
  ECHO Gradle wrapper jar not found at %WRAPPER_JAR%
  ECHO Bootstrapping wrapper jar from Gradle distribution...
  powershell -ExecutionPolicy Bypass -NoProfile -Command "& '%DIR%tools\bootstrap_gradle_wrapper.ps1'"
)

IF NOT EXIST "%WRAPPER_JAR%" (
  ECHO Failed to bootstrap Gradle wrapper jar. Check network/proxy and retry.
  EXIT /B 1
)

FOR %%A IN ("%WRAPPER_JAR%") DO SET FILESIZE=%%~zA
IF "%FILESIZE%"=="0" (
  ECHO Gradle wrapper jar is empty. Bootstrapping again...
  powershell -ExecutionPolicy Bypass -NoProfile -Command "& '%DIR%tools\bootstrap_gradle_wrapper.ps1'"
)

set JAVA_EXE=java.exe
IF NOT "%JAVA_HOME%"=="" set JAVA_EXE=%JAVA_HOME%\bin\java.exe

where "%JAVA_EXE%" >NUL 2>&1
IF %ERRORLEVEL% NEQ 0 (
  ECHO ERROR: JAVA_HOME is not set and no 'java' command could be found in your PATH.
  EXIT /B 1
)

set CLASSPATH=%WRAPPER_JAR%
set GRADLE_MAIN=org.gradle.wrapper.GradleWrapperMain

"%JAVA_EXE%" -classpath "%CLASSPATH%" %GRADLE_MAIN% %*

ENDLOCAL
@ECHO OFF
SETLOCAL

set DIR=%~dp0
set WRAPPER_JAR=%DIR%gradle\wrapper\gradle-wrapper.jar

IF NOT EXIST "%WRAPPER_JAR%" (
  ECHO Gradle wrapper jar not found at %WRAPPER_JAR%
  REM Try PowerShell bootstrap (no system Gradle required)
  powershell -ExecutionPolicy Bypass -File "%~dp0tools\bootstrap_gradle_wrapper.ps1"
)

FOR %%A IN ("%WRAPPER_JAR%") DO SET FILESIZE=%%~zA
IF "%FILESIZE%"=="0" (
  ECHO Gradle wrapper jar is empty. Bootstrapping via PowerShell downloader...
  powershell -ExecutionPolicy Bypass -File "%~dp0tools\bootstrap_gradle_wrapper.ps1"
)

IF NOT EXIST "%WRAPPER_JAR%" (
  ECHO Failed to bootstrap Gradle wrapper jar. Please check your network/proxy and retry.
  EXIT /B 1
)

set JAVA_EXE=java.exe
IF NOT "%JAVA_HOME%"=="" set JAVA_EXE=%JAVA_HOME%\bin\java.exe

where %JAVA_EXE% >NUL 2>&1
IF %ERRORLEVEL% NEQ 0 (
  ECHO ERROR: JAVA_HOME is not set and no 'java' command could be found in your PATH.
  EXIT /B 1
)

set CLASSPATH=%WRAPPER_JAR%
set GRADLE_MAIN=org.gradle.wrapper.GradleWrapperMain

"%JAVA_EXE%" -classpath "%CLASSPATH%" %GRADLE_MAIN% %*

ENDLOCAL

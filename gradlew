#!/usr/bin/env sh

APP_HOME=$(cd "$(dirname "$0")"; pwd -P)
WRAPPER_DIR="$APP_HOME/gradle/wrapper"
WRAPPER_JAR="$WRAPPER_DIR/gradle-wrapper.jar"
PROPS="$WRAPPER_DIR/gradle-wrapper.properties"

ensure_wrapper_jar() {
  if [ -s "$WRAPPER_JAR" ]; then
    return
  fi
  if [ ! -f "$PROPS" ]; then
    echo "Missing $PROPS; cannot bootstrap wrapper." >&2
    exit 1
  fi
  URL=$(grep -E '^\s*distributionUrl=' "$PROPS" | sed -E 's/^\s*distributionUrl=//' | sed 's#\\:#:#g')
  if [ -z "$URL" ]; then
    echo "distributionUrl not found in $PROPS" >&2
    exit 1
  fi
  mkdir -p "$WRAPPER_DIR"
  TMPZIP="$(mktemp 2>/dev/null || mktemp -t gradle).zip"
  echo "Downloading Gradle distribution: $URL"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$URL" -o "$TMPZIP" || true
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$TMPZIP" "$URL" || true
  else
    PY=python3; command -v $PY >/dev/null 2>&1 || PY=python
    $PY - "$URL" "$TMPZIP" << 'PY'
import sys, urllib.request
url, outp = sys.argv[1], sys.argv[2]
with urllib.request.urlopen(url) as r, open(outp,'wb') as f:
    f.write(r.read())
print(outp)
PY
  fi
  if [ ! -s "$TMPZIP" ]; then
    echo "Failed to download Gradle distribution. Check network/proxy." >&2
    exit 1
  fi
  echo "Extracting wrapper jar..."
  PY=python3; command -v $PY >/dev/null 2>&1 || PY=python
  $PY - "$TMPZIP" "$WRAPPER_DIR" << 'PY'
import sys, zipfile, os, shutil
zip_path, out_dir = sys.argv[1], sys.argv[2]
os.makedirs(out_dir, exist_ok=True)
with zipfile.ZipFile(zip_path,'r') as z:
    names = z.namelist()
    candidates = [n for n in names if n.endswith('.jar') and 'gradle-wrapper' in n]
    if not candidates:
        print('No gradle-wrapper-*.jar found in distribution', file=sys.stderr)
        sys.exit(1)
    target = candidates[0]
    tmp = os.path.join(out_dir, 'gradle-wrapper.jar.tmp')
    with z.open(target) as src, open(tmp,'wb') as dst:
        shutil.copyfileobj(src, dst)
    final = os.path.join(out_dir, 'gradle-wrapper.jar')
    os.replace(tmp, final)
    print('Wrote', final)
PY
  if [ ! -s "$WRAPPER_JAR" ]; then
    echo "Failed to extract gradle-wrapper.jar" >&2
    exit 1
  fi
}

ensure_wrapper_jar

if [ -n "$JAVA_HOME" ] ; then
    JAVACMD="$JAVA_HOME/bin/java"
else
    JAVACMD="java"
fi

if [ ! -x "$JAVACMD" ] ; then
    echo "ERROR: JAVA_HOME is not set and no 'java' command could be found in your PATH." 1>&2
    exit 1
fi

CLASSPATH="$WRAPPER_JAR"
GRADLE_MAIN=org.gradle.wrapper.GradleWrapperMain

exec "$JAVACMD" -classpath "$CLASSPATH" $GRADLE_MAIN "$@"
#!/usr/bin/env sh

##############################################################################
# Gradle start up script with bootstrap for missing wrapper jar
##############################################################################

APP_HOME=$(cd "$(dirname "$0")"; pwd -P)
WRAPPER_JAR="$APP_HOME/gradle/wrapper/gradle-wrapper.jar"

if [ ! -s "$WRAPPER_JAR" ]; then
  echo "Gradle wrapper jar not found at $WRAPPER_JAR"
  PROPS="$APP_HOME/gradle/wrapper/gradle-wrapper.properties"
  if [ ! -f "$PROPS" ]; then
    echo "Missing $PROPS; cannot bootstrap wrapper." >&2
    exit 1
  fi
  URL=$(grep -E '^\s*distributionUrl=' "$PROPS" | sed -E 's/^\s*distributionUrl=//' | sed 's#\\:#:#g')
  if [ -z "$URL" ]; then
    echo "distributionUrl not found in $PROPS" >&2
    exit 1
  fi
  TMPZIP="$(mktemp 2>/dev/null || mktemp -t gradle).zip"
  echo "Downloading Gradle distribution: $URL"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$URL" -o "$TMPZIP" || true
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$TMPZIP" "$URL" || true
  else
    PY=python3; command -v $PY >/dev/null 2>&1 || PY=python
    $PY - "$URL" "$TMPZIP" << 'PY'
import sys, urllib.request
url, outp = sys.argv[1], sys.argv[2]
with urllib.request.urlopen(url) as r, open(outp,'wb') as f:
    f.write(r.read())
print(outp)
PY
  fi

  if [ ! -s "$TMPZIP" ]; then
    echo "Failed to download Gradle distribution. Check network/proxy." >&2
    exit 1
  fi

  TMPDIR="$(mktemp -d 2>/dev/null || mktemp -d -t gradle)"
  echo "Extracting wrapper jar..."
  PY=python3; command -v $PY >/dev/null 2>&1 || PY=python
  $PY - "$TMPZIP" "$APP_HOME/gradle/wrapper" << 'PY'
import sys, zipfile, os, shutil, glob
zip_path, out_dir = sys.argv[1], sys.argv[2]
os.makedirs(out_dir, exist_ok=True)
with zipfile.ZipFile(zip_path,'r') as z:
    names = z.namelist()
    candidates = [n for n in names if n.endswith('.jar') and 'gradle-wrapper' in n]
    if not candidates:
        print('No gradle-wrapper-*.jar found in distribution', file=sys.stderr)
        sys.exit(1)
    target = candidates[0]
    tmp = os.path.join(out_dir, 'gradle-wrapper.jar.tmp')
    with z.open(target) as src, open(tmp,'wb') as dst:
        shutil.copyfileobj(src, dst)
    final = os.path.join(out_dir, 'gradle-wrapper.jar')
    os.replace(tmp, final)
    print('Wrote', final)
PY
  if [ ! -s "$WRAPPER_JAR" ]; then
    echo "Failed to extract gradle-wrapper.jar" >&2
    exit 1
  fi
fi

# Locate JAVA
if [ -n "$JAVA_HOME" ] ; then
    JAVACMD="$JAVA_HOME/bin/java"
else
    JAVACMD="java"
fi

if [ ! -x "$JAVACMD" ] ; then
    echo "ERROR: JAVA_HOME is not set and no 'java' command could be found in your PATH." 1>&2
    exit 1
fi

CLASSPATH=$WRAPPER_JAR
GRADLE_MAIN=org.gradle.wrapper.GradleWrapperMain

exec "$JAVACMD" -classpath "$CLASSPATH" $GRADLE_MAIN "$@"

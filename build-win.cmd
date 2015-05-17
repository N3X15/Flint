call pyinstaller main.spec
mkdir dist
mkdir dist\packages
copy /Y .packages.yml dist
copy /Y essentials.yml dist
xcopy /Y packages\*.xpi dist\packages
pause
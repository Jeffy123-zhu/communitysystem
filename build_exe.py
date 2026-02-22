import PyInstaller.__main__
import os
import shutil

# clean up old builds
if os.path.exists('dist'):
    shutil.rmtree('dist')
if os.path.exists('build'):
    shutil.rmtree('build')

# build the exe
PyInstaller.__main__.run([
    'launcher.py',
    '--name=CommunitySystem',
    '--onefile',
    '--windowed',
    '--add-data=templates;templates',
    '--add-data=database.py;.',
    '--add-data=app.py;.',
    '--hidden-import=flask',
    '--hidden-import=sqlite3',
    '--hidden-import=dateutil',
    '--hidden-import=webbrowser',
    '--hidden-import=threading',
    '--icon=NONE',
    '--clean',
])

print("\n" + "="*50)
print("Build complete!")
print("Executable location: dist/CommunitySystem.exe")
print("="*50)

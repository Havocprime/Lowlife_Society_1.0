# REVIEW FIRST! These are *suggested* moves.
# Use 'git mv' if this is a Git repo to preserve history.
# Any line starting with '#' is a comment. Remove the '#' to execute a move.

$ErrorActionPreference = 'Stop'

# Reason: Consolidate tags under src/cogs/tags to match 'src.cogs.tags'
# if (!(Test-Path 'GAME\src\cogs\tags')) { New-Item -ItemType Directory -Force -Path 'GAME\src\cogs\tags' | Out-Null }
# git mv 'GAME\src\tags\catalog.py' 'GAME\src\cogs\tags\catalog.py'

# Reason: Consolidate tags under src/cogs/tags to match 'src.cogs.tags'
# if (!(Test-Path 'GAME\src\cogs\tags')) { New-Item -ItemType Directory -Force -Path 'GAME\src\cogs\tags' | Out-Null }
# git mv 'GAME\src\tags\cog.py' 'GAME\src\cogs\tags\cog.py'

# Reason: Consolidate tags under src/cogs/tags to match 'src.cogs.tags'
# if (!(Test-Path 'GAME\src\cogs\tags')) { New-Item -ItemType Directory -Force -Path 'GAME\src\cogs\tags' | Out-Null }
# git mv 'GAME\src\tags\desktop.ini' 'GAME\src\cogs\tags\desktop.ini'

# Reason: Consolidate tags under src/cogs/tags to match 'src.cogs.tags'
# if (!(Test-Path 'GAME\src\cogs\tags')) { New-Item -ItemType Directory -Force -Path 'GAME\src\cogs\tags' | Out-Null }
# git mv 'GAME\src\tags\registry.py' 'GAME\src\cogs\tags\registry.py'

# Reason: Consolidate tags under src/cogs/tags to match 'src.cogs.tags'
# if (!(Test-Path 'GAME\src\cogs\tags')) { New-Item -ItemType Directory -Force -Path 'GAME\src\cogs\tags' | Out-Null }
# git mv 'GAME\src\tags\schema.py' 'GAME\src\cogs\tags\schema.py'

# Reason: Consolidate tags under src/cogs/tags to match 'src.cogs.tags'
# if (!(Test-Path 'GAME\src\cogs\tags\util')) { New-Item -ItemType Directory -Force -Path 'GAME\src\cogs\tags\util' | Out-Null }
# git mv 'GAME\src\tags\util\db.py' 'GAME\src\cogs\tags\util\db.py'

# Reason: Consolidate tags under src/cogs/tags to match 'src.cogs.tags'
# if (!(Test-Path 'GAME\src\cogs\tags\util')) { New-Item -ItemType Directory -Force -Path 'GAME\src\cogs\tags\util' | Out-Null }
# git mv 'GAME\src\tags\util\owners.py' 'GAME\src\cogs\tags\util\owners.py'

# Reason: Consolidate tags under src/cogs/tags to match 'src.cogs.tags'
# if (!(Test-Path 'GAME\src\cogs\tags\util')) { New-Item -ItemType Directory -Force -Path 'GAME\src\cogs\tags\util' | Out-Null }
# git mv 'GAME\src\tags\util\__init__.py' 'GAME\src\cogs\tags\util\__init__.py'

# Reason: Consolidate tags under src/cogs/tags to match 'src.cogs.tags'
# if (!(Test-Path 'GAME\src\cogs\tags\__pycache__')) { New-Item -ItemType Directory -Force -Path 'GAME\src\cogs\tags\__pycache__' | Out-Null }
# git mv 'GAME\src\tags\__pycache__\catalog.cpython-312.pyc' 'GAME\src\cogs\tags\__pycache__\catalog.cpython-312.pyc'

# Reason: Consolidate tags under src/cogs/tags to match 'src.cogs.tags'
# if (!(Test-Path 'GAME\src\cogs\tags\__pycache__')) { New-Item -ItemType Directory -Force -Path 'GAME\src\cogs\tags\__pycache__' | Out-Null }
# git mv 'GAME\src\tags\__pycache__\registry.cpython-312.pyc' 'GAME\src\cogs\tags\__pycache__\registry.cpython-312.pyc'

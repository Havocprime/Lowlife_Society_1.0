"""
Bridge module: the Discord extension name is 'src.cogs.tags', but the
implementation lives in 'src.tags'. This keeps imports consistent across the codebase.
"""
from src.cogs.tags.cog import setup  # re-export the extension entry point

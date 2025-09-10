# package marker

# --- Minimal async provider stub (replace with your real tags store) ---
async def _iter_players_with_damage_tags(self):
    """
    Yield (player_id, tags) for any player who currently has any of:
    wound.*, laceration.*, scratch.*, bruise.*, fractured_bone.*, broken_bone.*
    Implement this against your tag table/cog/state.
    """
    # Example against a hypothetical self.tags_svc.list_active(player_id)…
    # Here we just no-op yield nothing.
    if False:
        yield 0, []
    return
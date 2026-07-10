from app.models.world import PlayerState, WorldState


class HeartRateService:
    def update_player_hr(self, state: WorldState, player_id: str, heart_rate: int) -> PlayerState:
        player = state.players.get(player_id)
        if player is None:
            player = PlayerState(player_id=player_id, baseline_hr=80)
            state.players[player_id] = player

        player.heart_rate = int(heart_rate)
        player.stress = self.calculate_stress(player.heart_rate, player.baseline_hr)
        self.recalc_moon_rage(state)
        return player

    def calculate_stress(self, heart_rate: int, baseline_hr: int) -> float:
        return max(0.0, min(1.0, (heart_rate - baseline_hr) / 40.0))

    def recalc_moon_rage(self, state: WorldState) -> float:
        if not state.players:
            state.moon_rage = 0.0
            return state.moon_rage
        state.moon_rage = sum(player.stress for player in state.players.values()) / len(state.players)
        return state.moon_rage

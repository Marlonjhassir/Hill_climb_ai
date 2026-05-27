# Progreso del proyecto

## Fase actual: 2 — Juego Manual

## Último avance
- Fecha: 2026-05-26
- Archivo: `game/physics.py`
- Estado: completado y verificado
- Notas: PhysicsEngine con Space, gravedad 900 px/s², damping 0.9, collision handlers
  para jugador-terreno y rueda/chasis-moneda; flags player_touched_ground y
  coins_collected para comunicación con environment.py. ATENCIÓN API pymunk 7.x:
  usar on_collision(a, b, begin=cb) en lugar de add_collision_handler; callbacks
  retornan None (no bool); pass-through de monedas se logra con shape.sensor=True
  en coin.py, no con return False en el callback

## Siguiente paso
- Implementar `game/terrain.py` (generación del terreno con seed reproducible)
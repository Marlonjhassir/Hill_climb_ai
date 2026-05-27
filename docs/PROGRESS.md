# Progreso del proyecto

## Fase actual: 2 — Juego Manual

## Último avance
- Fecha: 2026-05-26
- Archivo: `game/terrain.py`
- Estado: completado y verificado
- Notas: terreno fijo de 21 puntos, cuerpo STATIC en pymunk, segmentos con
  friction=WHEEL_FRICTION y collision_type=COLLISION_TERRAIN; height_at() con
  np.interp y slope_at() con pendiente discreta; seed guardado para futura
  versión procedural sin cambiar la interfaz

## Siguiente paso
- Implementar `game/vehicle.py` (chasis + ruedas + motor con pymunk)
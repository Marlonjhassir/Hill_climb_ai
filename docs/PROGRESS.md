# Progreso del proyecto

## Fase actual: 2 — Juego Manual

## Último avance
- Fecha: 2026-05-27
- Archivo: `game/player.py`
- Estado: completado y verificado
- Notas: body pequeño (20x30 px, 0.8 kg) encima del chasis; PivotJoint fija
  posición + GearJoint(ratio=1) sincroniza rotación; friction=0 en shape para
  no interferir en el frame de colisión; COLLISION_PLAYER activa el flag
  player_touched_ground en physics.py

## Siguiente paso
- Implementar `game/camera.py` (seguimiento horizontal con lerp)
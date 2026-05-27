# Progreso del proyecto

## Fase actual: 3 — Sistema de Recompensas

## Fase 2 — Juego Manual ✅ (completada 2026-05-27)

### Archivos implementados (en orden estricto)
| Archivo | Estado | Notas |
|---|---|---|
| `config/settings.py` | ✅ | Escrito por el usuario, verificado |
| `game/physics.py` | ✅ | pymunk 7.x: on_collision, VEHICLE_GROUP |
| `game/terrain.py` | ✅ | 21 puntos fijos, zona plana en spawn (x=0..300) |
| `game/vehicle.py` | ✅ | ShapeFilter, MOTOR_MAX_FORCE=50000, rate negado |
| `game/player.py` | ✅ | ShapeFilter(group=VEHICLE_GROUP) |
| `game/camera.py` | ✅ | Lerp frame-rate independent |
| `game/ui.py` | ✅ | Panel semitransparente + barra de tiempo |
| `game/environment.py` | ✅ | Orquestador; get_state() y _compute_reward() son stubs |
| `main.py` | ✅ | Game loop, D/→ acelera, A/← frena, reset tras 1 s |

### Bugs corregidos durante verificación
- **ShapeFilter faltante**: ruedas y chasis se solapaban 20.5px, pymunk generaba
  impulsos destructivos en cada frame. FIX: `VEHICLE_GROUP=1` aplicado a todas las
  shapes del vehículo y conductor.
- **Pendiente en zona de spawn**: la normal al suelo tenía componente horizontal
  que empujaba el vehículo fuera del mapa. FIX: zona plana x=0..300 en terrain.py.
- **Dirección del motor invertida**: `rate = +ACCELERATION_RATE * net` avanzaba
  a la izquierda. FIX: `rate = -ACCELERATION_RATE * net`.
- **Potencia insuficiente**: MOTOR_MAX_FORCE=8000 daba ~512 N; la primera colina
  requería ~695 N. FIX: MOTOR_MAX_FORCE=50000 (~3200 N disponibles).

### Comportamiento verificado al cierre de fase
- Vehículo estable al nacer (sin input)
- D/→ avanza, A/← frena/retrocede
- Game over cuando el conductor toca el suelo
- Episodio se reinicia automáticamente tras 1 segundo
- Vehículo puede recorrer todo el terreno en < 20 s

---

## Último avance
- Fecha: 2026-05-27
- Archivo: — (inicio de Fase 3, pendiente de comenzar)
- Estado: en espera de instrucción para arrancar

## Siguiente paso — Fase 3: Sistema de Recompensas
Orden de archivos (estricto):
1. `game/coin.py` — moneda física con sensor=True para pass-through
2. `game/checkpoint.py` — checkpoint que añade tiempo al episodio
3. `ai/reward_system.py` — recompensa por frame (para análisis y futuro DRL)
4. Implementar `_compute_reward()` en `environment.py` usando reward_system
5. Conectar monedas y checkpoints al entorno en `environment.py`
# Progreso del proyecto

## Fase actual: 4 — Estados de IA

## Fase 1 — Preparación ✅ (completada por el usuario)

Estructura de carpetas, entorno virtual, dependencias instaladas, git inicializado.

---

## Fase 2 — Juego Manual ✅ (completada 2026-05-27)

### Archivos implementados
| Archivo | Estado | Notas |
|---|---|---|
| `config/settings.py` | ✅ | Escrito por el usuario, verificado |
| `game/physics.py` | ✅ | pymunk 7.x: on_collision, VEHICLE_GROUP |
| `game/terrain.py` | ✅ | 21 puntos fijos, zona plana en spawn (x=0..300) |
| `game/vehicle.py` | ✅ | ShapeFilter, MOTOR_MAX_FORCE=50000, rate negado |
| `game/player.py` | ✅ | ShapeFilter(group=VEHICLE_GROUP) |
| `game/camera.py` | ✅ | Lerp frame-rate independent |
| `game/ui.py` | ✅ | Panel semitransparente + barra de tiempo |
| `game/environment.py` | ✅ | Orquestador; get_state() stub |
| `main.py` | ✅ | Game loop, D/→ acelera, A/← frena, reset tras 1 s |

### Bugs corregidos durante verificación
- **ShapeFilter faltante**: ruedas y chasis se solapaban 20.5px → VEHICLE_GROUP=1 a todas las shapes.
- **Pendiente en zona de spawn**: normal con componente horizontal empujaba el vehículo. FIX: zona plana x=0..300.
- **Dirección del motor invertida**: `rate = -ACCELERATION_RATE * net`.
- **Potencia insuficiente**: MOTOR_MAX_FORCE=8000 → 50000.

---

## Fase 3 — Sistema de Recompensas ✅ (completada 2026-05-27)

### Archivos implementados
| Archivo | Estado | Notas |
|---|---|---|
| `game/coin.py` | ✅ | Body STATIC, sensor=True, COLLISION_COIN=5 |
| `game/checkpoint.py` | ✅ | Segment vertical sensor=True, CHECKPOINT_WIDTH=8, CHECKPOINT_HEIGHT=200 |
| `ai/reward_system.py` | ✅ | compute_reward() pura: progreso + velocidad + muerte |
| `game/environment.py` | ✅ | Integración completa: coins, checkpoints, reward |

### Detalles de integración en environment.py
- `_coin_map: dict[shape→Coin]`: 19 monedas cada 200 px desde x=400 hasta x=4000.
- `_checkpoint_map: dict[shape→Checkpoint]`: 5 puertas en x=700, 1400, 2100, 2800, 3500.
- `step()`: pop(shape, None) para recolección segura (anti-duplicados).
- `_delta_distance`: calculado como max_distance - prev_max cada frame.
- `_compute_reward()`: delega a compute_reward(velocity_x, delta_distance, done).
- `render()`: capas coins y checkpoints entre terreno y vehículo, con culling.

### Resultado verificado
- Monedas doradas visibles en intervalos regulares ✅
- 5 postes verdes con bandera blanca ✅
- Score aumenta al recoger moneda ✅
- Tiempo aumenta al cruzar checkpoint ✅
- HUD refleja cambios en tiempo real ✅

---

## Deuda técnica — Fase 8

### Comportamiento de checkpoints: acumular vs. resetear

**Problema:** el plan maestro describe `MAX_TIME` como "segundos *sin checkpoint* → muerte",
lo que implica un contador de inactividad que se *resetea* al cruzar un checkpoint.
La implementación actual lo trata como tiempo acumulable (`time_left += CHECKPOINT_TIME`).

**Impacto en terreno fijo (Fases 2-7):** ninguno observable. El tiempo máximo sigue siendo
acotado (20 + 5×10 = 70 s) y el comportamiento del juego es correcto.

**Impacto potencial en Fase 8 (terreno procedural):** si el mapa generado coloca checkpoints
en zonas densas, el vehículo podría cruzarlos todos rápido y luego tener tiempo libre
sin incentivo para avanzar. El enfoque reset-en-checkpoint forzaría al agente a llegar
al siguiente checkpoint antes de que el contador llegue a cero.

**Acción pendiente para Fase 8:** decidir si `time_left += CHECKPOINT_TIME` (acumulativo,
actual) o `time_left = MAX_TIME + CHECKPOINT_TIME` (reset, según el plan). Evaluar con
terreno procedural cuál produce mejor comportamiento de aprendizaje.

---

## Último avance
- Fecha: 2026-05-27
- Archivos: `game/coin.py`, `game/checkpoint.py`, `ai/reward_system.py`, `game/environment.py`
- Estado: Fase 3 completada y verificada visualmente

## Siguiente paso
- Fase 4: implementar `get_state()` en `game/environment.py`
  - 14 entradas según sección 4.11 del plan maestro
  - Verificar rangos en `experiments/plots.ipynb`
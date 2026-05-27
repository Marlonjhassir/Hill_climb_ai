"""
ai/reward_system.py — Recompensa instantánea por frame.

Responsabilidades:
  - Calcular un escalar de recompensa a partir del estado del vehículo
    en el frame actual.
  - Exponer una única función pública: compute_reward().

Contexto de uso:
  - environment._compute_reward() llama a esta función cada frame.
  - El resultado es útil para graficar el aprendizaje y para una eventual
    extensión a Deep Reinforcement Learning (Fase 8).
  - NO influye en el algoritmo genético, que usa la función de fitness
    (distancia + 50 × monedas) calculada al final de cada episodio.

Prohibido: modificar estado del juego, acceder a pymunk, importar pygame.
           Esta función debe ser PURA: mismo input → mismo output siempre.
"""

# ---------------------------------------------------------------------------
# Constantes de la función de recompensa
# ---------------------------------------------------------------------------

# Factor de escala para el progreso de distancia.
# Cada píxel de avance hacia la derecha suma este valor a la recompensa.
# Un factor de 1.0 hace que la recompensa sea directamente proporcional
# al progreso en píxeles — fácil de interpretar en las gráficas.
DIST_REWARD_FACTOR: float = 1.0

# Factor de escala para la velocidad instantánea.
# Es mucho más pequeño que DIST_REWARD_FACTOR porque la velocidad ya está
# implícita en el progreso: un vehículo rápido acumula mucho delta_distance.
# Este término añade un pequeño impulso para mantener la velocidad incluso
# cuando el vehículo ya alcanzó el máximo histórico de distancia.
SPEED_REWARD_FACTOR: float = 0.01

# Penalización al terminar el episodio con el conductor tocando el suelo.
# Debe ser negativa y lo suficientemente grande para que el agente aprenda
# a evitar volcarse, pero no tan grande que domine sobre la recompensa
# acumulada de un episodio largo.
DEATH_PENALTY: float = -100.0


# ---------------------------------------------------------------------------
# Función pública
# ---------------------------------------------------------------------------

def compute_reward(
    velocity_x: float,
    delta_distance: float,
    is_done: bool,
) -> float:
    """
    Calcula la recompensa instantánea del frame actual.

    La recompensa tiene tres componentes:

    1. Progreso (main signal):
       max(0, delta_distance) × DIST_REWARD_FACTOR
       Solo cuenta si el vehículo superó su máximo histórico de distancia.
       max(0, ...) evita recompensa negativa por retroceder — la falta de
       progreso ya es una penalización implícita por no ganar puntos.

    2. Velocidad (bonus secundario):
       max(0, velocity_x) × SPEED_REWARD_FACTOR
       Premia mantener impulso incluso cuando no se avanza al máximo.
       Ejemplo: subiendo una colina sin superar el récord de distancia,
       el agente igual recibe una pequeña señal positiva por moverse.

    3. Penalización por muerte:
       DEATH_PENALTY si is_done es True.
       Señal fuerte para que el agente aprenda a no volcarse.

    Rango típico de salida:
      - Frame normal avanzando: > 0
      - Frame parado o retrocediendo: 0.0
      - Frame final (volcado): ~ DEATH_PENALTY (negativo)

    Args:
        velocity_x:     velocidad horizontal del chasis en px/s.
                        Positivo = avanzando a la derecha.
                        Fuente: vehicle.chassis.velocity.x
        delta_distance: cuántos píxeles se ganó en max_distance este frame.
                        Positivo solo si se superó el récord histórico.
                        Fuente: calculado en environment.step()
        is_done:        True si el episodio terminó en este frame
                        (conductor tocó el suelo o tiempo agotado).

    Returns:
        Escalar de recompensa para el frame actual.
    """
    reward = 0.0

    # Componente 1: progreso real (solo avance neto, nunca negativo)
    # max(0, ...) es importante: si el vehículo retrocede, delta_distance
    # puede ser 0 (max_distance no se actualiza hacia atrás), por lo que
    # este término simplemente no aporta nada en ese caso.
    reward += max(0.0, delta_distance) * DIST_REWARD_FACTOR

    # Componente 2: bono de velocidad instantánea (solo hacia adelante)
    # Complementa el progreso: si el agente va rápido pero aún no supera
    # el récord de distancia (por ejemplo, en el primer segundo de un
    # nuevo episodio), igualmente recibe señal positiva.
    reward += max(0.0, velocity_x) * SPEED_REWARD_FACTOR

    # Componente 3: penalización por fin de episodio con muerte
    # Se añade en el último frame del episodio para distinguir entre
    # "el tiempo se agotó" (sin penalización extra) y "el conductor cayó"
    # (penalización grande). Sin esta distinción, el agente podría aprender
    # a quedarse quieto para no arriesgarse a volcarse.
    if is_done:
        reward += DEATH_PENALTY

    return reward
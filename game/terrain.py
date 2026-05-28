"""
game/terrain.py — Generación procedural del terreno.

Responsabilidades:
  - Generar la forma del suelo mediante suma de sinusoides con seed configurable.
  - Añadir el terreno al Space de pymunk como cuerpo estático.
  - Exponer height_at(x) y slope_at(x) para dominio abierto (cualquier x >= 0).

Diseño (sub-fase 8.1):
  Suma de 4 sinusoides con frecuencias y amplitudes fijas, pero fases
  aleatorias seeded. Cada seed produce un perfil distinto y reproducible.
  La amplitud escala con la distancia al spawn para dificultad creciente.

Prohibido: renderizar nada, contener lógica de juego, acceder a pygame.
"""

import math

import numpy as np
import pymunk

from config.settings import TERRAIN_SEED_DEFAULT, WHEEL_FRICTION
from game.physics import COLLISION_TERRAIN

# ---------------------------------------------------------------------------
# Constantes de forma del terreno
# ---------------------------------------------------------------------------

# Zona plana al inicio: los primeros 400 px son completamente horizontales.
# Sin esta zona, la normal al suelo en el spawn tendría componente horizontal
# que empuja el vehículo antes de que la IA pueda reaccionar (bug de Fase 2).
_FLAT_ZONE_END: float = 400.0

# Altura base del terreno en coordenadas pygame (Y positivo hacia abajo).
# Un valor de 500 deja ~220 px de cielo visible y ~220 px de tierra debajo.
_BASE_Y: float = 500.0

# Dificultad creciente: la amplitud escala linealmente desde 0× (al salir
# de la zona plana) hasta _MAX_AMP_FACTOR× (a _AMP_SCALE_DISTANCE px más allá).
# Pasada esa distancia, el factor se mantiene fijo en el máximo.
#
# Relación factor ↔ pendiente máxima (derivada de la suma de ondas):
#   max_slope_teorica = _MAX_AMP_FACTOR × Σ(amp_i × freq_i) ≈ factor × 0.872 px/px
#   Con factor=2.0 → max_slope ≈ 1.74 px/px → atan(1.74) ≈ 60°.
#   Esto es el peor caso teórico (todos los cosenos al máximo a la vez).
#   En la práctica las pendientes serán inferiores (~20-40°).
_AMP_SCALE_DISTANCE: float = 3000.0  # px recorridos hasta dificultad máxima
_MAX_AMP_FACTOR:     float = 1.7     # cap de pendiente maxima ~60°

# ---------------------------------------------------------------------------
# Definición de las cuatro ondas (período px, amplitud base px)
# ---------------------------------------------------------------------------
# Cuatro ondas superpuestas producen un perfil suficientemente orgánico:
#   macro-A (T=2200): grandes colinas bien separadas
#   macro-B (T=1400): colinas medianas; rompe la regularidad de macro-A
#   medium  (T=700):  cuestas cortas, más frecuentes
#   micro   (T=280):  rugosidad superficial (base para obstáculos en 8.2)
_WAVE_DEFS: tuple[tuple[float, float], ...] = (
    (2200.0, 70.0),
    (1400.0, 50.0),
    (700.0,  25.0),
    (280.0,  10.0),
)

# ---------------------------------------------------------------------------
# Constantes de muestreo para pymunk
# ---------------------------------------------------------------------------

# Paso entre puntos consecutivos al construir los segmentos físicos (px).
# Con T_min=280 px y paso=20, hay ~14 muestras por ciclo → error < 1 px.
_PHYS_SAMPLE_STEP: int = 20

# Límite derecho del terreno físico (px). El vehículo cae (done=True) al
# superarlo; 10000 px cubre con margen una sesión de entrenamiento completa.
_PHYS_X_MAX: float = 10000.0


class Terrain:
    """
    Genera el terreno proceduralmente y lo registra en pymunk como cuerpo estático.

    La forma del terreno se define como:
        height_at(x) = BASE_Y + amp_factor(x) · Σ amp_i · sin(freq_i · x + phase_i)

    donde las fases phase_i son aleatorias según el seed, y amp_factor(x) crece
    con la distancia para aumentar la dificultad de forma gradual.

    Dos propiedades clave:
      - Determinismo: dado el mismo seed, height_at(x) devuelve siempre
        el mismo valor para el mismo x. No hay estado oculto.
      - Dominio abierto: height_at(x) funciona para cualquier x >= 0;
        no hay límite en el terreno hacia la derecha.

    Uso típico desde environment.py:
        terrain = Terrain(space=engine.get_space(), seed=42)
        y      = terrain.height_at(300)      # altura del suelo en x=300
        slope  = terrain.slope_at(300)       # pendiente en x=300
    """

    def __init__(self, space: pymunk.Space, seed: int = TERRAIN_SEED_DEFAULT) -> None:
        """
        Args:
            space: el pymunk.Space activo (creado por PhysicsEngine).
            seed:  semilla de reproducibilidad. Mismo seed → mismo perfil siempre.
        """
        self._seed = seed

        # Lista de (freq, amp_base, phase) generada a partir del seed.
        # Se almacena para evaluar height_at() / slope_at() en cualquier x,
        # en cualquier momento, sin regenerar la secuencia aleatoria.
        self._waves: list[tuple[float, float, float]] = []
        self._generate_waves(seed)

        # Agrega segmentos físicos al Space muestreando height_at().
        self._add_to_space(space)

    # ------------------------------------------------------------------
    # Generación de ondas
    # ------------------------------------------------------------------

    def _generate_waves(self, seed: int) -> None:
        """
        Calcula las fases aleatorias de cada onda usando el seed.

        Por qué np.random.default_rng y no np.random.seed():
            default_rng crea un generador LOCAL, independiente del estado
            global de np.random. Si usáramos np.random.seed() aquí, afectaría
            a GeneticAlgorithm, Genome.mutate y cualquier otro código que use
            np.random — efecto colateral peligroso y difícil de debuggear.

        Args:
            seed: entero arbitrario que inicializa el generador.
        """
        rng = np.random.default_rng(seed)

        self._waves = []
        for period, amp_base in _WAVE_DEFS:
            # Fase aleatoria en [0, 2π) → desplaza la onda horizontalmente.
            # Con dos seeds distintos obtenemos fases distintas → perfiles distintos.
            phase = float(rng.uniform(0.0, 2.0 * math.pi))
            # Frecuencia angular: ω = 2π / T (unidades: rad/px)
            freq  = 2.0 * math.pi / period
            self._waves.append((freq, amp_base, phase))

    # ------------------------------------------------------------------
    # Registro en pymunk
    # ------------------------------------------------------------------

    def _add_to_space(self, space: pymunk.Space) -> None:
        """
        Muestrea height_at() a intervalos regulares y crea los segmentos
        físicos del terreno como cuerpo estático en el Space de pymunk.

        Por qué Body.STATIC y no Body.DYNAMIC con masa enorme:
            El cuerpo estático le dice a pymunk que nunca se mueve.
            pymunk lo trata de forma especial (no integra fuerzas ni
            velocidades sobre él), lo que mejora rendimiento y estabilidad.

        Por qué muestrear height_at() en lugar de precomputing una lista:
            height_at() es una función analítica; muestrearla es trivial y
            siempre da el mismo resultado. Precomputar una lista fija sería
            redundante y limitaría la extensión futura del terreno.
        """
        self._body = pymunk.Body(body_type=pymunk.Body.STATIC)

        prev_x = 0.0
        prev_y = self.height_at(prev_x)
        curr_x = float(_PHYS_SAMPLE_STEP)

        segments: list[pymunk.Segment] = []

        while curr_x <= _PHYS_X_MAX + _PHYS_SAMPLE_STEP:
            curr_y = self.height_at(curr_x)

            # Segment(body, punto_a, punto_b, radius).
            # radius=2: grosor que evita el "tunneling" — si un objeto rápido
            # recorre más de 2 px en un frame, el radio actúa como buffer y
            # la colisión se detecta igualmente (sin radio, podría atravesar).
            seg = pymunk.Segment(
                self._body,
                (prev_x, prev_y),
                (curr_x, curr_y),
                radius=2,
            )
            seg.friction       = WHEEL_FRICTION
            seg.collision_type = COLLISION_TERRAIN

            segments.append(seg)
            prev_x, prev_y = curr_x, curr_y
            curr_x += _PHYS_SAMPLE_STEP

        # Añadir body Y todas sus shapes de una sola llamada.
        # Añadir solo las shapes sin el body es el error más frecuente con
        # pymunk: las shapes existen en memoria pero no participan en colisiones.
        space.add(self._body, *segments)

    # ------------------------------------------------------------------
    # Consultas de terreno (usadas por la cámara, la IA y el render)
    # ------------------------------------------------------------------

    def height_at(self, x: float) -> float:
        """
        Devuelve la coordenada y del suelo en la posición x (coords mundo).

        Para x <= _FLAT_ZONE_END devuelve _BASE_Y (zona plana del spawn).
        Para x > _FLAT_ZONE_END evalúa la suma de sinusoides escalada por
        el factor de dificultad de la distancia.

        Convención de ejes (pygame/pymunk): Y positivo apunta hacia ABAJO.
          - y pequeño → terreno ALTO en pantalla (cima de colina).
          - y grande  → terreno BAJO en pantalla (valle).

        Dominio: cualquier x >= 0. Sin límite derecho.

        Args:
            x: coordenada horizontal en píxeles (coords mundo).

        Returns:
            y del suelo en esa x.
        """
        if x <= _FLAT_ZONE_END:
            # Zona plana: normal al suelo 100% vertical → vehículo sin empuje
            # lateral al nacer. Fix permanente del bug detectado en Fase 2.
            return _BASE_Y

        # Factor de amplitud: crece de 0× a _MAX_AMP_FACTOR× en _AMP_SCALE_DISTANCE px.
        # Empieza en 0 en x=_FLAT_ZONE_END → la transición desde la zona plana
        # es suave (tanto y como dy/dx son continuos en el límite).
        # progress=0 → salida del spawn, terreno casi plano.
        # progress=1 → dificultad máxima; min() capa más allá.
        progress   = (x - _FLAT_ZONE_END) / _AMP_SCALE_DISTANCE
        amp_factor = min(progress, 1.0) * _MAX_AMP_FACTOR

        # Suma de las cuatro sinusoides centrada en 0, luego desplazada a _BASE_Y.
        # Cada onda contribuye: amp_base × amp_factor × sin(freq × x + phase).
        # La suma oscila alrededor de 0; sumar _BASE_Y la ancla al nivel de referencia.
        offset = sum(
            amp * amp_factor * math.sin(freq * x + phase)
            for freq, amp, phase in self._waves
        )

        return _BASE_Y + offset

    def slope_at(self, x: float, eps: float = 1.0) -> float:
        """
        Devuelve la pendiente del terreno en la posición x.

        Usa diferenciación numérica centrada de orden 2:
            slope ≈ (height_at(x + ε) − height_at(x − ε)) / (2ε)

        Por qué numérica y no la derivada analítica:
            La derivada de amp_factor(x) · Σ amp·sin(freq·x+phase) requiere
            aplicar la regla del producto sobre amp_factor(x), que produce
            términos discontinuos en x = _FLAT_ZONE_END + _AMP_SCALE_DISTANCE.
            Con ε=1 px el error numérico es O(ε²/T²) < 10⁻⁵ para el período
            mínimo (280 px) — despreciable para la IA y para el render.

        Interpretación del signo (Y positivo hacia abajo):
          - Valor positivo → bajada (terreno desciende en dirección de marcha).
          - Valor negativo → subida (vehículo contra la cuesta).
          - Cero          → plano.

        Args:
            x:   coordenada horizontal en píxeles.
            eps: semi-paso de diferenciación. Default 1.0 px.

        Returns:
            Pendiente adimensional (ΔY/ΔX, px/px).
        """
        # En x < eps evaluaríamos x-eps < 0 (fuera del dominio).
        # Diferencia hacia adelante para ese caso borde.
        if x < eps:
            return (self.height_at(x + eps) - self.height_at(x)) / eps

        return (self.height_at(x + eps) - self.height_at(x - eps)) / (2.0 * eps)
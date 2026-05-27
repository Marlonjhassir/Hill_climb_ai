"""
game/terrain.py — Generación y representación física del terreno.

Responsabilidades:
  - Generar la lista de puntos (x, y) que definen la forma del suelo.
  - Añadir el terreno al Space de pymunk como cuerpo estático.
  - Exponer height_at(x) y slope_at(x) para la cámara y el vector de estado de la IA.

Versión actual: terreno fijo (puntos predefinidos).
Versión futura (Fase 8): terreno procedural por suma de sinusoides con seed.
"""

import numpy as np
import pymunk

from config.settings import WHEEL_FRICTION
from game.physics import COLLISION_TERRAIN


class Terrain:
    """
    Genera el terreno y lo registra en pymunk como cuerpo estático.

    Uso típico desde environment.py:
        terrain = Terrain(space=engine.get_space(), seed=42)
        y = terrain.height_at(300)      # altura del suelo en x=300
        s = terrain.slope_at(300)       # pendiente en x=300
    """

    def __init__(self, space: pymunk.Space, seed: int = 0) -> None:
        """
        Args:
            space: el pymunk.Space activo (creado por PhysicsEngine).
            seed:  semilla para reproducibilidad. No se usa en la versión
                   fija, pero se guarda para cuando implementemos el terreno
                   procedural sin tener que cambiar la interfaz.
        """
        self._seed = seed

        # Lista de tuplas (x, y) en coordenadas de mundo (píxeles).
        # Y positivo apunta hacia abajo (igual que pygame y pymunk).
        # Un y pequeño = terreno alto en pantalla (cima de colina).
        # Un y grande = terreno bajo en pantalla (valle).
        self.points: list[tuple[float, float]] = []

        self._generate(seed)
        self._add_to_space(space)

    # ------------------------------------------------------------------
    # Generación del terreno
    # ------------------------------------------------------------------

    def _generate(self, seed: int) -> None:
        """
        Define la forma del terreno como lista de puntos ordenados por x.

        Versión 1 — terreno fijo: ignoramos el seed y usamos puntos
        codificados a mano. Esto nos permite verificar la física sin
        introducir variabilidad aleatoria que complique el debugging.

        Convención de alturas (SCREEN_HEIGHT = 720):
          - y ≈ 500  →  suelo a unos 220px del borde inferior (nivel base).
          - y ≈ 350  →  cima de colina alta.
          - El vehículo nace en x≈100, y≈490 (justo encima del suelo inicial).
        """
        self.points = [
            # (x,    y)     — comentario de referencia
            # Zona de spawn plana: x=0..300 a y=500.
            # CRÍTICO: si el spawn cae sobre una pendiente, la normal al suelo
            # tiene componente horizontal que empuja el vehículo hacia un lado.
            # Una zona plana garantiza que la normal sea 100% vertical al nacer.
            (0,    500),   # inicio — zona de spawn (plana)
            (300,  500),   # fin zona plana; a partir de aquí empiezan las colinas
            (500,  510),   # primera bajada suave
            (700,  490),
            (900,  440),   # primera subida
            (1100, 400),   # primera cima
            (1300, 450),   # bajada al valle
            (1500, 480),
            (1700, 420),   # segunda subida
            (1900, 360),   # segunda cima (más alta)
            (2100, 410),
            (2300, 470),   # valle central
            (2500, 430),
            (2700, 370),   # tercera subida pronunciada
            (2900, 310),   # tercera cima (la más alta)
            (3100, 360),
            (3300, 420),   # bajada larga
            (3500, 450),
            (3700, 400),
            (3900, 340),   # cuarta colina
            (4100, 380),   # final del terreno fijo
        ]

    # ------------------------------------------------------------------
    # Registro en pymunk
    # ------------------------------------------------------------------

    def _add_to_space(self, space: pymunk.Space) -> None:
        """
        Crea los segmentos físicos del terreno y los añade al Space.

        Por qué Body.STATIC y no Body.DYNAMIC con masa grande:
          El cuerpo estático le dice a pymunk "este objeto nunca se mueve".
          pymunk lo trata de forma especial internamente (no calcula fuerzas
          sobre él). Si usáramos DYNAMIC con masa enorme, pymunk igualmente
          lo procesaría como móvil y el comportamiento físico sería incorrecto.
        """
        # Cuerpo estático: sin masa, sin inercia, nunca se desplaza.
        self._body = pymunk.Body(body_type=pymunk.Body.STATIC)

        segments: list[pymunk.Segment] = []

        for i in range(len(self.points) - 1):
            p1 = self.points[i]
            p2 = self.points[i + 1]

            # Segment(body, punto_a, punto_b, radius)
            # radius=2: grosor del segmento en píxeles. Sin grosor, objetos
            # pequeños y rápidos pueden "tunnelear" (atravesar el segmento
            # en un solo frame si van muy rápido). El radio actúa como buffer.
            seg = pymunk.Segment(self._body, p1, p2, radius=2)

            # Fricción heredada de settings.py. Controla cuánto agarre tienen
            # las ruedas sobre el suelo. 1.5 es un valor alto (más que el
            # estándar de 1.0) para compensar que la física simulada no
            # modela la deformación del neumático.
            seg.friction = WHEEL_FRICTION

            # Etiqueta de colisión: physics.py la usa para detectar contactos
            # con el jugador y activar el flag player_touched_ground.
            seg.collision_type = COLLISION_TERRAIN

            segments.append(seg)

        # Añadimos el body y TODAS sus shapes de una vez.
        # Olvidar añadir el body (solo añadir shapes) es el bug más frecuente
        # con pymunk: las shapes existen pero no interactúan con nada.
        space.add(self._body, *segments)

    # ------------------------------------------------------------------
    # Consultas de terreno (usadas por la cámara y la IA)
    # ------------------------------------------------------------------

    def height_at(self, x: float) -> float:
        """
        Devuelve la coordenada y del terreno en la posición x.

        Usa np.interp, que hace interpolación lineal entre los dos puntos
        más cercanos a x. Para x fuera del rango del terreno, devuelve
        el y del extremo más cercano (extrapolación constante por defecto).

        Args:
            x: coordenada horizontal en píxeles (coordenadas de mundo).

        Returns:
            y del suelo en esa x. Un y menor significa terreno más alto.
        """
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        # np.interp(valor, puntos_x, puntos_y) → y interpolado
        return float(np.interp(x, xs, ys))

    def slope_at(self, x: float) -> float:
        """
        Devuelve la pendiente del terreno en la posición x.

        Pendiente = (y2 - y1) / (x2 - x1) entre los puntos que rodean a x.
        Interpretación en coordenadas pygame (Y↓):
          - Valor positivo  → terreno desciende (y crece hacia abajo).
          - Valor negativo  → terreno asciende (cuesta arriba para el vehículo).
          - Valor cero      → terreno plano.

        La IA usa este valor como una de sus 14 entradas para anticipar
        si viene una subida antes de llegar a ella.

        Args:
            x: coordenada horizontal en píxeles.

        Returns:
            Pendiente adimensional (ΔY/ΔX, en px/px).
        """
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]

        # Buscar el segmento que contiene a x
        for i in range(len(xs) - 1):
            if xs[i] <= x <= xs[i + 1]:
                dx = xs[i + 1] - xs[i]
                if dx == 0:
                    return 0.0
                return (ys[i + 1] - ys[i]) / dx

        # x fuera del rango: usar la pendiente del extremo más cercano
        if x < xs[0]:
            return (ys[1] - ys[0]) / (xs[1] - xs[0])
        return (ys[-1] - ys[-2]) / (xs[-1] - xs[-2])
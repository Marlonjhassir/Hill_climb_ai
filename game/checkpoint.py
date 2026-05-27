"""
game/checkpoint.py — Checkpoint de tiempo: puerta vertical en el terreno.

Responsabilidades:
  - Crear un segmento vertical estático con sensor=True en el Space.
  - Marcar la shape con COLLISION_CHECKPOINT para que physics.py detecte
    el cruce del vehículo.
  - Exponer collect() para que environment.py lo elimine y sume el tiempo.

El bono de tiempo (CHECKPOINT_TIME segundos) lo aplica environment.py,
no este módulo. Aquí solo existe el objeto físico y su ciclo de vida.

Prohibido: modificar time_left, gestionar el score, dibujar.
"""

import pymunk

from game.physics import COLLISION_CHECKPOINT

# ---------------------------------------------------------------------------
# Constantes del checkpoint
# ---------------------------------------------------------------------------
# Ancho (radio) del Segment. El ancho total de detección es 2 × CHECKPOINT_WIDTH.
# Con radio=8 → 16 px totales. Las ruedas (radio=25) no pueden esquivarlo.
CHECKPOINT_WIDTH  = 8    # px — radio del Segment

# Altura del poste por encima del terreno.
# 200 px cubre el rango vertical del vehículo (ruedas ~25 px + chasis ~35 px +
# conductor ~30 px = ~90 px). El margen extra garantiza visibilidad y detección.
CHECKPOINT_HEIGHT = 200  # px — distancia desde el suelo hasta la cima del poste


class Checkpoint:
    """
    Puerta vertical estática que el vehículo cruza para ganar tiempo extra.

    Usa un Segment vertical sensor=True: detecta el cruce pero no bloquea
    físicamente al vehículo. Al ser cruzado, environment.py llama collect()
    que lo elimina del Space para que no pueda contarse dos veces.

    Uso típico desde environment.py:
        cp = Checkpoint(space, x=800, terrain_y=terrain.height_at(800))
        # ... vehículo cruza el checkpoint ...
        # physics.py activa checkpoints_crossed → environment.py llama:
        cp.collect(space)
        env.time_left += CHECKPOINT_TIME
    """

    def __init__(
        self,
        space: pymunk.Space,
        x: float,
        terrain_y: float,
    ) -> None:
        """
        Crea el checkpoint y lo añade al Space.

        Args:
            space:      Space activo de PhysicsEngine.
            x:          coordenada horizontal del checkpoint en mundo (px).
            terrain_y:  altura del suelo en esa x (terrain.height_at(x)).
                        El segmento se extiende desde aquí hacia arriba.
        """
        self._active = True
        self._setup_body(x, terrain_y)
        self._add_to_space(space)

    # ------------------------------------------------------------------
    # Construcción interna
    # ------------------------------------------------------------------

    def _setup_body(self, x: float, terrain_y: float) -> None:
        """Crea el cuerpo estático y el Segment sensor vertical."""

        # Body.STATIC: el checkpoint no se mueve ni cae.
        # Posicionamos el body en (x, terrain_y) para que las coordenadas
        # locales del Segment sean intuitivas: (0, 0) = suelo, (0, -H) = cima.
        self.body = pymunk.Body(body_type=pymunk.Body.STATIC)
        self.body.position = (x, terrain_y)

        # Segment(body, punto_a, punto_b, radius):
        #   Los puntos están en coordenadas LOCALES del body.
        #   Con el body en (x, terrain_y):
        #     (0,  0)              → mundo (x, terrain_y)          = base del poste
        #     (0, -CHECKPOINT_HEIGHT) → mundo (x, terrain_y - 200) = cima del poste
        #   Y negativo en coords locales = hacia arriba en pantalla,
        #   porque Y positivo apunta hacia abajo en nuestro sistema.
        self.shape = pymunk.Segment(
            self.body,
            (0, -CHECKPOINT_HEIGHT),   # cima del poste
            (0,  0),                   # base del poste (nivel del suelo)
            CHECKPOINT_WIDTH,
        )

        # sensor=True: el vehículo pasa a través sin ser bloqueado.
        self.shape.sensor = True

        # Etiqueta para los handlers de physics.py. Distinta de COLLISION_COIN
        # para que environment.py pueda tratar monedas y checkpoints por separado.
        self.shape.collision_type = COLLISION_CHECKPOINT

    def _add_to_space(self, space: pymunk.Space) -> None:
        """Añade el body y la shape al Space."""
        space.add(self.body, self.shape)

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def collect(self, space: pymunk.Space) -> None:
        """
        Marca el checkpoint como usado y lo elimina del Space.

        Una vez eliminado, ninguna shape del vehículo puede volver a
        activar el handler → el bono de tiempo se aplica una sola vez.

        Args:
            space: el mismo Space al que se añadió en __init__.
        """
        if not self._active:
            # Protección contra llamadas duplicadas en el mismo frame.
            return
        self._active = False
        space.remove(self.body, self.shape)

    # ------------------------------------------------------------------
    # Propiedades de acceso (usadas por environment.py al renderizar)
    # ------------------------------------------------------------------

    @property
    def active(self) -> bool:
        """True mientras el checkpoint no haya sido cruzado."""
        return self._active

    @property
    def position_x(self) -> float:
        """Coordenada x del checkpoint en mundo (para transformar con cámara)."""
        return float(self.body.position.x)

    @property
    def terrain_y(self) -> float:
        """Coordenada y del suelo en este checkpoint (base del poste)."""
        return float(self.body.position.y)
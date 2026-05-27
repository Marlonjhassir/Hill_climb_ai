"""
game/coin.py — Moneda física coleccionable.

Responsabilidades:
  - Crear un cuerpo estático en el Space de pymunk con shape sensor.
  - Marcar la shape con COLLISION_COIN para que physics.py detecte
    cuándo una rueda o el chasis la toca.
  - Exponer remove_from_space() para que environment.py la elimine
    al ser recogida.

Prohibido: contener lógica de puntuación, dibujar, mover la moneda.
           Toda esa responsabilidad vive en environment.py.
"""

import pymunk

from game.physics import COLLISION_COIN

# ---------------------------------------------------------------------------
# Constantes de la moneda
# ---------------------------------------------------------------------------
COIN_RADIUS   = 12    # px — radio de la shape de detección y del círculo dibujado
COIN_VALUE    = 1     # puntos que añade al score del episodio al ser recogida
# Distancia vertical por encima del suelo a la que flota la moneda.
# Las ruedas tienen radio=25 px, así que su centro está 25 px sobre el suelo
# y su parte más alta llega a 50 px. Con offset=35, la moneda queda dentro
# del "barrido" de la rueda sin importar micro-variaciones de terreno.
COIN_Y_OFFSET = 35    # px — flotación sobre la superficie del terreno


class Coin:
    """
    Moneda estática con detección de colisión sin respuesta física.

    La moneda usa un Body STATIC (no recibe fuerzas, no cae) y una Shape
    con sensor=True (detecta solapamientos pero no aplica impulsos). Esto
    permite que el vehículo la atraviese mientras el callback de colisión
    en physics.py sigue disparándose para registrar la recolección.

    Uso típico desde environment.py:
        coin = Coin(space, x=500, y=terrain.height_at(500) - COIN_Y_OFFSET)
        # ... el vehículo toca la moneda ...
        # physics.py activa coins_collected → environment.py llama:
        coin.remove_from_space(space)
    """

    def __init__(
        self,
        space: pymunk.Space,
        x: float,
        y: float,
    ) -> None:
        """
        Crea la moneda y la añade al Space.

        Args:
            space: Space activo de PhysicsEngine.
            x:     coordenada horizontal en mundo (px).
            y:     coordenada vertical en mundo (px).
                   Calcular desde environment.py como:
                   terrain.height_at(x) - COIN_Y_OFFSET
        """
        self._setup_body(x, y)
        self._add_to_space(space)

    # ------------------------------------------------------------------
    # Construcción interna
    # ------------------------------------------------------------------

    def _setup_body(self, x: float, y: float) -> None:
        """Crea el cuerpo estático y la shape sensor de la moneda."""

        # Body.STATIC: pymunk sabe que este cuerpo NUNCA se moverá.
        # No necesita masa ni inercia. Internamente pymunk lo trata de forma
        # especial (no calcula fuerzas sobre él), lo que lo hace más eficiente
        # que un cuerpo dinámico con masa muy grande.
        self.body = pymunk.Body(body_type=pymunk.Body.STATIC)
        self.body.position = (x, y)

        # Circle: shape circular centrada en el body.
        self.shape = pymunk.Circle(self.body, COIN_RADIUS)

        # sensor=True: la forma sigue participando en la detección de
        # colisiones (el callback COLLISION_COIN se disparará), pero NO
        # aplica ningún impulso físico. Sin este flag, la moneda bloquearía
        # al vehículo como si fuera una pared sólida.
        self.shape.sensor = True

        # Etiqueta de colisión para el handler en physics.py.
        # IMPORTANTE: no asignar VEHICLE_GROUP al filter de esta shape.
        # Las monedas deben quedar en el grupo 0 (por defecto), distinto
        # del grupo 1 del vehículo; de lo contrario nunca se detectarían.
        self.shape.collision_type = COLLISION_COIN

    def _add_to_space(self, space: pymunk.Space) -> None:
        """Añade el body y la shape al Space."""
        # Hay que añadir AMBOS: si solo añadieras la shape, el body no
        # existiría en la simulación y no se dispararían las colisiones.
        space.add(self.body, self.shape)

    # ------------------------------------------------------------------
    # Acceso y ciclo de vida
    # ------------------------------------------------------------------

    @property
    def position(self) -> pymunk.Vec2d:
        """Posición de la moneda en coordenadas de mundo."""
        return self.body.position

    def remove_from_space(self, space: pymunk.Space) -> None:
        """
        Elimina la moneda del Space (moneda recogida).

        Debe llamarse desde environment.py después de confirmar la
        recolección. Eliminar del Space evita que el handler siga
        disparándose en frames posteriores para esta misma moneda.

        Args:
            space: el mismo Space al que se añadió en __init__.
        """
        # Hay que eliminar tanto la shape como el body.
        # Si solo eliminas la shape, el body queda huérfano en el Space
        # y pymunk puede comportarse de forma inesperada.
        space.remove(self.body, self.shape)
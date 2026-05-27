"""
game/physics.py — Motor de física del juego.

Responsabilidades:
  - Crear y mantener el pymunk.Space global.
  - Configurar gravedad y constantes de simulación desde config/settings.py.
  - Registrar collision handlers y exponer flags de eventos para environment.py.
  - Exponer step(dt) para avanzar la simulación un frame.

Prohibido: dibujar nada, contener lógica de juego (puntaje, episodio, IA).
"""

import pymunk

from config.settings import GRAVITY

# ---------------------------------------------------------------------------
# Tipos de colisión
# ---------------------------------------------------------------------------
# pymunk identifica cada categoría de cuerpo con un entero único llamado
# collision_type. Cuando dos shapes colisionan, pymunk busca el handler
# registrado para ese par de enteros y ejecuta sus callbacks.
# Definimos las constantes aquí para que los demás módulos (vehicle, terrain,
# player, coin) las importen y las asignen a sus shapes al crearlas.
COLLISION_TERRAIN = 1
COLLISION_CHASSIS = 2
COLLISION_WHEEL   = 3
COLLISION_PLAYER  = 4
COLLISION_COIN    = 5

# ---------------------------------------------------------------------------
# Grupos de colisión (ShapeFilter)
# ---------------------------------------------------------------------------
# pymunk.ShapeFilter(group=N): shapes con el mismo N > 0 NO colisionan entre sí,
# pero SÍ colisionan con shapes de otros grupos (incluido el grupo 0 por defecto).
#
# VEHICLE_GROUP agrupa chasis + ruedas + conductor.
# Por qué es CRÍTICO:
#   Las ruedas (radio=25px) se solapan geométricamente con el chasis (offset=22px,
#   mitad_alto=17.5px → diferencia=4.5px). Sin este filtro, pymunk aplica impulsos
#   de separación ENORMES entre ruedas y chasis cada frame → vehículo inestable.
#   Lo mismo ocurre con el conductor, cuyo borde inferior toca el borde superior
#   del chasis.
VEHICLE_GROUP: int = 1


class PhysicsEngine:
    """
    Encapsula el pymunk.Space y los handlers de colisión del juego.

    Uso típico desde environment.py:
        engine = PhysicsEngine()
        space  = engine.get_space()
        # ... añadir cuerpos al space ...
        engine.step(1 / 60)
        if engine.player_touched_ground:
            done = True
    """

    def __init__(self) -> None:
        # pymunk.Space es el contenedor de la simulación. Todos los cuerpos
        # (Body) y formas (Shape) deben añadirse a este objeto para existir.
        self.space = pymunk.Space()

        # Gravedad: vector (x, y) en píxeles/s².
        # Y positivo apunta hacia abajo (igual que en pygame), así (0, GRAVITY)
        # hace que los objetos caigan. Si lo pusieras negativo, flotarían.
        self.space.gravity = (0, GRAVITY)

        # Damping: factor de amortiguación de velocidad por segundo [0.0, 1.0].
        # 1.0 = sin pérdida de energía (sin aire); 0.9 = cada segundo el cuerpo
        # conserva el 90% de su velocidad. Simula resistencia del aire.
        # Sin damping, el vehículo ganaría velocidad indefinidamente en bajadas.
        self.space.damping = 0.9

        # ------------------------------------------------------------------
        # Flags de eventos — el "buzón" entre physics.py y environment.py
        # ------------------------------------------------------------------
        # physics.py los activa dentro de los callbacks de colisión.
        # environment.py los lee después de cada step() y actúa en consecuencia.
        # NUNCA modificamos el Space desde dentro de un callback (pymunk lo
        # prohíbe; causa crashes). En cambio, guardamos la referencia aquí y
        # dejamos que environment.py haga la limpieza después.

        # True si el cuerpo del jugador tocó el terreno en este frame.
        self.player_touched_ground: bool = False

        # Lista de shapes de monedas que fueron tocadas en este frame.
        # environment.py las elimina del Space y actualiza el score.
        self.coins_collected: list[pymunk.Shape] = []

        self._setup_collision_handlers()

    # ------------------------------------------------------------------
    # Configuración de collision handlers
    # ------------------------------------------------------------------

    def _setup_collision_handlers(self) -> None:
        """
        Registra los handlers entre categorías de cuerpos.

        API de pymunk 7.x: on_collision(tipo_A, tipo_B, begin=callback, ...)
          - Los callbacks se pasan como parámetros keyword, no como atributos.
          - 'begin' se llama en el PRIMER frame de contacto.
          - Los callbacks devuelven None (no bool). Para que las monedas sean
            pass-through (no empujen el vehículo), su shape debe tener
            sensor=True — esto se configura en coin.py cuando creemos las monedas.
        """

        # --- Jugador vs Terreno -------------------------------------------
        # Cuando el conductor toca el suelo, el episodio termina.
        self.space.on_collision(
            COLLISION_PLAYER, COLLISION_TERRAIN,
            begin=self._on_player_ground_begin,
        )

        # --- Rueda vs Moneda -----------------------------------------------
        # La rueda es el elemento más probable de tocar una moneda en el suelo.
        self.space.on_collision(
            COLLISION_WHEEL, COLLISION_COIN,
            begin=self._on_coin_collected,
        )

        # --- Chasis vs Moneda ---------------------------------------------
        # Por si una moneda está elevada y la rueda no la alcanza primero.
        self.space.on_collision(
            COLLISION_CHASSIS, COLLISION_COIN,
            begin=self._on_coin_collected,
        )

    def _on_player_ground_begin(
        self,
        _arbiter: pymunk.Arbiter,
        _space: pymunk.Space,
        _data: object,
    ) -> None:
        """
        Callback: el cuerpo del jugador entró en contacto con el terreno.

        En pymunk 7.x los callbacks devuelven None; pymunk aplica la física
        normal de colisión por defecto (el jugador no atraviesa el suelo).
        Solo necesitamos activar el flag para que environment.py lo lea.
        """
        self.player_touched_ground = True

    def _on_coin_collected(
        self,
        arbiter: pymunk.Arbiter,
        _space: pymunk.Space,
        _data: object,
    ) -> None:
        """
        Callback: una rueda o el chasis tocó una moneda.

        Identificamos la shape de la moneda buscando cuál de las dos shapes
        del arbiter tiene collision_type == COLLISION_COIN. No asumimos el
        orden porque pymunk no garantiza que shapes[0] sea siempre tipo_A.

        El efecto pass-through (moneda no empuja el vehículo) se logra
        marcando la shape de la moneda como sensor=True al crearla en
        coin.py — no hace falta retornar nada aquí en pymunk 7.x.
        """
        for shape in arbiter.shapes:
            if shape.collision_type == COLLISION_COIN:
                # Guardamos la referencia; environment.py la eliminará del Space.
                self.coins_collected.append(shape)
                break

    # ------------------------------------------------------------------
    # Loop de simulación
    # ------------------------------------------------------------------

    def step(self, dt: float) -> None:
        """
        Avanza la simulación física un paso de tiempo 'dt' segundos.

        Args:
            dt: delta de tiempo en segundos. Debe ser pequeño y constante
                (idealmente 1/60 ≈ 0.0167 s). Si dt varía mucho, los cuerpos
                pueden 'tunnelear' (atravesar paredes) o explotar numéricamente.

        Los flags se limpian ANTES de space.step() para que solo reflejen
        eventos del frame actual, no acumulados de frames anteriores.
        """
        # Limpiar eventos del frame anterior
        self.player_touched_ground = False
        self.coins_collected.clear()

        # Avanzar la simulación: pymunk calcula fuerzas, resuelve restricciones
        # y colisiones, y actualiza posiciones y velocidades de todos los cuerpos.
        self.space.step(dt)

    # ------------------------------------------------------------------
    # Acceso al Space
    # ------------------------------------------------------------------

    def get_space(self) -> pymunk.Space:
        """
        Devuelve el Space para que otros módulos añadan sus cuerpos.

        Solo environment.py debería llamar a este método. Los módulos de
        terrain, vehicle y player reciben el Space como argumento en su
        constructor; no lo buscan por su cuenta. Esto mantiene el flujo
        de dependencias en una sola dirección.
        """
        return self.space
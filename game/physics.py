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
COLLISION_TERRAIN     = 1
COLLISION_CHASSIS     = 2
COLLISION_WHEEL       = 3
COLLISION_PLAYER      = 4
COLLISION_COIN        = 5
COLLISION_CHECKPOINT  = 6

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
        engine.register_wheel_shapes(vehicle.back_wheel_shape,
                                     vehicle.front_wheel_shape)
        engine.step(1 / 60)
        if engine.player_touched_ground:
            done = True
        back_contact  = engine.back_wheel_on_ground
        front_contact = engine.front_wheel_on_ground
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
        # Referencias a las shapes de ruedas — usadas en el handler de contacto
        # ------------------------------------------------------------------
        # physics.py necesita saber cuál shape es la rueda trasera y cuál la
        # delantera para poder distinguirlas dentro del callback wheel-terrain.
        # Se inicializan a None; environment.py llama register_wheel_shapes()
        # tras crear el vehículo para establecerlas.
        self._back_wheel_shape:  pymunk.Shape | None = None
        self._front_wheel_shape: pymunk.Shape | None = None

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

        # True si la rueda trasera/delantera está en contacto con el terreno.
        # Se usa en get_state() para que la IA sepa si el vehículo tiene tracción.
        self.back_wheel_on_ground:  bool = False
        self.front_wheel_on_ground: bool = False

        # Lista de shapes de monedas tocadas en este frame.
        # environment.py las elimina del Space y actualiza el score.
        self.coins_collected: list[pymunk.Shape] = []

        # Lista de shapes de checkpoints cruzados en este frame.
        # Se usa lista (no bool) para identificar cuál checkpoint eliminar.
        # La comprobación 'not in' evita duplicados si rueda Y chasis cruzan
        # el mismo checkpoint en el mismo step.
        self.checkpoints_crossed: list[pymunk.Shape] = []

        self._setup_collision_handlers()

    # ------------------------------------------------------------------
    # Registro de shapes de ruedas
    # ------------------------------------------------------------------

    def register_wheel_shapes(
        self,
        back:  pymunk.Shape,
        front: pymunk.Shape,
    ) -> None:
        """
        Registra las shapes de rueda para el handler de contacto con terreno.

        Debe llamarse desde environment.py después de crear el vehículo, antes
        del primer step(). Sin esta llamada, back_wheel_on_ground y
        front_wheel_on_ground permanecerán siempre en False.

        Por qué necesitamos esto:
            Ambas ruedas comparten COLLISION_WHEEL = 3. El handler wheel-terrain
            no puede saber por tipo de colisión cuál es cuál; necesita comparar
            la shape concreta del arbiter contra referencias guardadas aquí.

        Args:
            back:  shape de la rueda trasera (vehicle.back_wheel_shape).
            front: shape de la rueda delantera (vehicle.front_wheel_shape).
        """
        self._back_wheel_shape  = back
        self._front_wheel_shape = front

    # ------------------------------------------------------------------
    # Configuración de collision handlers
    # ------------------------------------------------------------------

    def _setup_collision_handlers(self) -> None:
        """
        Registra los handlers entre categorías de cuerpos.

        API de pymunk 7.x: on_collision(tipo_A, tipo_B, begin=cb, pre_solve=cb, ...)
          - 'begin' se llama en el PRIMER frame de contacto.
          - 'pre_solve' se llama CADA frame mientras el contacto persiste.
          - Los callbacks devuelven None. Para que las monedas sean pass-through,
            su shape debe tener sensor=True (configurado en coin.py).

        Elección begin vs pre_solve:
          - Jugador, monedas, checkpoints → 'begin': son eventos puntuales
            (la primera vez que se tocan es lo que importa).
          - Rueda vs terreno → 'pre_solve': necesitamos saber si la rueda
            ACTUALMENTE está en contacto (información de estado continuo),
            no solo si empezó a tocar. Con begin + clear-en-step(), el flag
            se borraría antes de que begin vuelva a disparar → siempre False.
        """

        # --- Jugador vs Terreno -------------------------------------------
        # Cuando el conductor toca el suelo, el episodio termina.
        self.space.on_collision(
            COLLISION_PLAYER, COLLISION_TERRAIN,
            begin=self._on_player_ground_begin,
        )

        # --- Rueda vs Terreno (contacto continuo para get_state) ----------
        # pre_solve dispara cada frame mientras la rueda toca el suelo.
        # Borramos los flags ANTES de space.step(), pre_solve los re-activa
        # durante space.step() si el contacto sigue vivo.
        self.space.on_collision(
            COLLISION_WHEEL, COLLISION_TERRAIN,
            pre_solve=self._on_wheel_ground_pre_solve,
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

        # --- Rueda vs Checkpoint ------------------------------------------
        # El cruce normal: la rueda delantera llega primero al checkpoint.
        self.space.on_collision(
            COLLISION_WHEEL, COLLISION_CHECKPOINT,
            begin=self._on_checkpoint_crossed,
        )

        # --- Chasis vs Checkpoint -----------------------------------------
        # Backup: si la rueda pasa por debajo de la base del checkpoint,
        # el chasis lo detecta igualmente.
        self.space.on_collision(
            COLLISION_CHASSIS, COLLISION_CHECKPOINT,
            begin=self._on_checkpoint_crossed,
        )

    # ------------------------------------------------------------------
    # Callbacks de colisión
    # ------------------------------------------------------------------

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

    def _on_wheel_ground_pre_solve(
        self,
        arbiter: pymunk.Arbiter,
        _space: pymunk.Space,
        _data: object,
    ) -> None:
        """
        Callback: una rueda está en contacto con el terreno en este frame.

        Se llama con 'pre_solve', que dispara cada frame durante el contacto.
        Combinado con el borrado de flags al inicio de step(), esto garantiza
        que los flags solo son True mientras el contacto está activo.

        Identifica cuál rueda es comparando la shape del arbiter contra las
        referencias guardadas en register_wheel_shapes().
        """
        for shape in arbiter.shapes:
            if shape.collision_type == COLLISION_WHEEL:
                # Comparamos la identidad del objeto (is), no el valor,
                # porque dos shapes distintas pueden tener el mismo tipo.
                if shape is self._back_wheel_shape:
                    self.back_wheel_on_ground = True
                elif shape is self._front_wheel_shape:
                    self.front_wheel_on_ground = True
                break

    def _on_checkpoint_crossed(
        self,
        arbiter: pymunk.Arbiter,
        _space: pymunk.Space,
        _data: object,
    ) -> None:
        """
        Callback: una rueda o el chasis cruzó un checkpoint.

        Identificamos la shape del checkpoint (collision_type == CHECKPOINT)
        y la añadimos a la lista solo si aún no estaba, para evitar sumar
        el bono dos veces cuando rueda + chasis cruzan en el mismo step.
        """
        for shape in arbiter.shapes:
            if shape.collision_type == COLLISION_CHECKPOINT:
                # 'not in' evita el duplicado si múltiples shapes del vehículo
                # activan el handler en el mismo frame de simulación.
                if shape not in self.checkpoints_crossed:
                    self.checkpoints_crossed.append(shape)
                break

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
        En particular, back/front_wheel_on_ground se ponen a False aquí y
        el callback pre_solve los vuelve a activar si el contacto persiste.
        """
        # Limpiar eventos del frame anterior
        self.player_touched_ground = False
        self.back_wheel_on_ground  = False
        self.front_wheel_on_ground = False
        self.coins_collected.clear()
        self.checkpoints_crossed.clear()

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
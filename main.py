"""
main.py — Punto de entrada del juego Hill Climb AI.

Responsabilidades:
  - Inicializar pygame y crear la ventana.
  - Correr el game loop: leer teclado → step → render → flip.
  - Reiniciar el episodio automáticamente cuando done=True.
  - Parsear --mode y --seed desde la terminal.

Prohibido: contener física, lógica de IA, dibujar directamente.
           Toda esa lógica vive en game/environment.py.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pygame
import torch

from ai.genetic_algorithm import GeneticAlgorithm
from ai.genome import Genome
from config.settings import FPS, MODEL_DIR, SCREEN_HEIGHT, SCREEN_WIDTH
from game.environment import Environment

# Segundos que la pantalla permanece congelada al terminar el episodio,
# para que el jugador pueda ver la posición final antes del reinicio.
_RESET_DELAY_S = 1.0


def _parse_args() -> argparse.Namespace:
    """
    Lee los argumentos de la línea de comandos.

    Returns:
        Namespace con atributos:
            mode (str): modo de ejecución.
            seed (int): semilla del terreno para reproducibilidad.
    """
    parser = argparse.ArgumentParser(
        description="Hill Climb AI — juego con física y aprendizaje neuroevolutivo."
    )
    parser.add_argument(
        "--mode",
        choices=["play", "train", "random_ai", "watch", "demo"],
        default="play",
        help=(
            "'play' para control manual, "
            "'random_ai' para ver una red con pesos aleatorios, "
            "'watch' para ver el mejor genoma entrenado (carga best_genome.pt), "
            "'train' para entrenamiento neuroevolutivo, "
            "'demo' para visualizar la evolución generación a generación (sin persistencia)."
        ),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="Semilla del terreno. Mismo número = mismo mapa.",
    )
    return parser.parse_args()


def _build_action(keys: pygame.key.ScancodeWrapper) -> tuple[float, float]:
    """
    Convierte el estado actual del teclado en una acción (accel, brake).

    La IA en fases posteriores generará valores continuos en [0.0, 1.0].
    El teclado usa 0.0 o 1.0 (binario), suficiente para el modo manual.

    Teclas:
        D / Flecha derecha → acelerar
        A / Flecha izquierda → frenar

    Args:
        keys: resultado de pygame.key.get_pressed(), indexado por K_*.

    Returns:
        (accel, brake) ambos en {0.0, 1.0}.
    """
    # get_pressed() devuelve el ESTADO de cada tecla en este instante,
    # no un evento puntual. Esto es crucial: si el jugador mantiene 'D'
    # apretada durante 3 segundos, cada frame devolverá accel=1.0,
    # mientras que un evento KEYDOWN solo se dispararía una vez.
    accel = 1.0 if (keys[pygame.K_d] or keys[pygame.K_RIGHT]) else 0.0
    brake = 1.0 if (keys[pygame.K_a] or keys[pygame.K_LEFT]) else 0.0
    return accel, brake


def _load_best_genome() -> tuple[Genome, float, int]:
    """
    Carga el mejor genoma entrenado desde MODEL_DIR/best_genome.pt.

    Si el archivo no existe, imprime un mensaje claro y termina el proceso
    con código de error 1. No tiene sentido arrancar el modo watch sin un
    genoma previamente entrenado.

    Qué hace torch.load():
        Deserializa el dict que guardamos en trainer._save_checkpoint():
        {'weights': torch.Tensor(470,), 'fitness': float, 'generation': int}.
        Es pickle especializado de PyTorch; reconoce tensores guardados con
        torch.save() y los reconstruye en memoria sin pasar por numpy.

    Returns:
        (genome, fitness, generation): el Genome reconstruido y sus metadatos.
    """
    best_path = Path(MODEL_DIR) / "best_genome.pt"

    if not best_path.exists():
        # Mensaje accionable: le decimos exactamente cómo solucionar el problema.
        print(
            f"[watch] Error: no se encontró '{best_path}'.\n"
            f"        Primero entrena con: python main.py --mode train"
        )
        sys.exit(1)

    # weights_only=False porque el dict guardado contiene escalares Python
    # (float, int) además del tensor de pesos. PyTorch >= 2.0 requiere
    # especificarlo explícitamente para evitar el warning; es seguro aquí
    # porque el archivo lo generamos nosotros mismos en trainer.py.
    data = torch.load(best_path, weights_only=False)

    genome = Genome()

    # data['weights'] es torch.Tensor (470,); set_weights() espera np.ndarray.
    # .numpy() comparte el buffer de memoria con el tensor (sin copia) cuando
    # el tensor está en CPU, que es siempre nuestro caso en este proyecto.
    genome.set_weights(data['weights'].numpy())

    fitness:    float = float(data['fitness'])
    generation: int   = int(data['generation'])

    print(
        f"[watch] Genoma cargado — generación {generation}, "
        f"fitness {fitness:.1f}"
    )
    return genome, fitness, generation


def _run_demo(
    surface: pygame.Surface,
    clock:   pygame.time.Clock,
    seed:    int,
) -> None:
    """
    Modo demo: entrena y visualiza el mejor genoma de cada generación.

    Ciclo por generación:
      1. Entrenamiento headless — todos los individuos juegan seed fijo, sin render.
      2. Visualización del mejor genoma con render a 60 FPS hasta fin de episodio.
      3. Pausa de _RESET_DELAY_S segundos (igual que los otros modos).
      4. Evolucionar la población y volver al paso 1.

    Por qué seed fijo para todas las generaciones:
        Permite observar cómo el MISMO terreno se conquista progresivamente
        mejor a lo largo del tiempo. Si el seed cambiara cada gen, sería
        imposible saber si el agente mejoró o simplemente tuvo más suerte
        con un terreno más fácil.

    Sin persistencia: no guarda checkpoints, no carga nada de disco.
    Arranca siempre desde la generación 0.

    Args:
        surface: Surface principal de pygame (ya inicializada).
        clock:   Clock para regular los FPS durante la visualización.
        seed:    Semilla del terreno. Pasar --seed N desde CLI para variarla.
    """
    # Paso de tiempo FIJO para el entrenamiento.
    # A diferencia del DT variable de clock.tick(), el DT fijo garantiza que
    # el mismo genoma produce el mismo resultado en cualquier ejecución.
    _DT        = 1.0 / FPS
    _MAX_STEPS = 10_000    # tope de seguridad por episodio (~167 s a 60 FPS)

    ga         = GeneticAlgorithm()
    population = ga.initialize()

    # Dos entornos distintos para separar la fase rápida (sin render)
    # de la fase visual (con render). Cada uno tiene su propio Space pymunk.
    env_train = Environment(seed=seed)   # resetea por individuo, nunca renderiza
    env_show  = Environment(seed=seed)   # resetea por generación, renderiza a 60 FPS

    gen = 0

    while True:
        # ----------------------------------------------------------------
        # Fase 1 — Entrenamiento headless
        # ----------------------------------------------------------------
        pygame.display.set_caption(
            f"Hill Climb AI — demo | entrenando gen {gen + 1}  "
            f"({len(population)} individuos)..."
        )

        for genome in population:
            # Vaciar la cola de eventos una vez por individuo.
            # Sin esto el SO marca la ventana como "(No responde)" en ~5 s.
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

            env_train.reset(seed=seed)
            state = env_train.get_state()

            for _ in range(_MAX_STEPS):
                action = genome.forward(state)
                state, _, done, _ = env_train.step(action, _DT)
                if done:
                    break

            # Misma fórmula que Trainer (sección 7.4 de CLAUDE.md)
            genome.fitness = env_train.max_distance + 50.0 * env_train.score

        # Recoger métricas ANTES de evolve(), que resetea fitness a 0.
        fitnesses = [g.fitness for g in population]
        best      = max(population, key=lambda g: g.fitness)
        best_fit  = best.fitness
        avg_fit   = sum(fitnesses) / len(fitnesses)

        print(
            f"[demo] Gen {gen + 1:>3} | "
            f"mejor: {best_fit:>8.1f} | "
            f"promedio: {avg_fit:>8.1f}"
        )

        # ----------------------------------------------------------------
        # Fase 2 — Visualización del mejor genoma
        # ----------------------------------------------------------------
        env_show.reset(seed=seed)
        env_show.generation   = gen + 1
        env_show.best_fitness = best_fit
        pygame.display.set_caption(
            f"Hill Climb AI — demo | gen {gen + 1} | fitness {best_fit:.0f}"
        )

        current_state: np.ndarray = np.zeros(14, dtype=np.float32)
        waiting_reset: bool       = False
        reset_timer:   float      = 0.0

        # Bucle de visualización: corre hasta que la pausa post-episodio expira.
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

            dt_ms = clock.tick(FPS)
            dt    = dt_ms / 1000.0

            if waiting_reset:
                reset_timer += dt
                if reset_timer >= _RESET_DELAY_S:
                    break  # pausa completada → pasar a la siguiente generación
                env_show.render(surface)
                pygame.display.flip()
                continue

            action = best.forward(current_state)
            new_state, _, done, _ = env_show.step(action, dt)
            current_state = np.array(new_state, dtype=np.float32)

            env_show.render(surface)
            pygame.display.flip()

            if done:
                waiting_reset = True

        # ----------------------------------------------------------------
        # Fase 3 — Evolucionar y repetir
        # ----------------------------------------------------------------
        population = ga.evolve()
        gen += 1


def main() -> None:
    """
    Game loop principal. Inicializa pygame, corre el juego y sale limpiamente.

    Flujo por frame:
      1. Vaciar la cola de eventos del sistema (QUIT, etc.).
      2. clock.tick(FPS) → mide el dt real de este frame.
      3. Si estamos en pausa post-episodio: renderizar y contar tiempo.
      4. Leer teclado / red neuronal → acción.
      5. env.step(action, dt) → avanza la simulación.
      6. env.render(surface) → dibuja el frame.
      7. pygame.display.flip() → muestra el frame en pantalla.
      8. Si done: entrar en pausa → reset cuando expire el timer.
    """
    args = _parse_args()

    # ------------------------------------------------------------------
    # Inicialización de pygame
    # ------------------------------------------------------------------
    pygame.init()

    # set_mode crea la ventana y devuelve la Surface principal.
    # Esta Surface es el "lienzo" donde se dibujan todos los elementos.
    # Todo lo que pintemos sobre ella solo se hace visible después de flip().
    surface = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Hill Climb AI")

    # Clock controla el framerate.
    # clock.tick(FPS): duerme lo necesario para no superar FPS fotogramas/s
    # y devuelve los milisegundos reales transcurridos (puede ser > 1000/FPS
    # si el CPU estuvo ocupado con otra tarea).
    clock = pygame.time.Clock()

    # El modo demo tiene su propio bucle completo (entrena + visualiza).
    # Lo despachamos aquí, antes de crear el env del juego normal, para no
    # ejecutar código innecesario (env, genome, etc.) que demo no necesita.
    if args.mode == "demo":
        _run_demo(surface, clock, seed=args.seed)
        return

    env = Environment(seed=args.seed)

    # ------------------------------------------------------------------
    # Selección del controlador según el modo
    # ------------------------------------------------------------------
    # 'play'      → teclado (genome=None, se lee pygame.key.get_pressed()).
    # 'random_ai' → Genome con pesos Kaiming aleatorios, sin entrenar.
    # 'watch'     → mejor Genome guardado en disco por trainer.py.
    # Los tres modos comparten el mismo game loop; la diferencia es solo
    # qué objeto genera la acción en cada frame.
    genome: Genome | None

    if args.mode == "random_ai":
        genome = Genome()

    elif args.mode == "watch":
        # _load_best_genome() hace sys.exit(1) si el archivo no existe,
        # así que si llegamos aquí el genoma está garantizado.
        genome, fitness, generation = _load_best_genome()

        # El checkpoint almacena generation en base 0 (gen 4 = 5ª generación).
        # El HUD usa base 1, así que sumamos 1 para que coincida con lo que
        # el usuario ve en los logs de entrenamiento ("Gen 0" = primera).
        env.generation   = generation + 1
        env.best_fitness = fitness

        # Actualizamos el título de la ventana con los metadatos del genoma,
        # para que el usuario sepa qué generación y fitness está observando.
        pygame.display.set_caption(
            f"Hill Climb AI — watch | gen {generation + 1} | fitness {fitness:.0f}"
        )

    else:
        # 'play' y 'train' — en 'train' main.py no se usa; el entrenamiento
        # corre completamente en trainer.py en modo headless.
        genome = None

    # Estado del frame anterior para alimentar la red neuronal.
    # El primer frame usa ceros (el vehículo aún no se ha movido).
    current_state: np.ndarray = np.zeros(14, dtype=np.float32)

    # Acumulador para la pausa al final del episodio
    reset_timer: float = 0.0
    waiting_reset: bool = False

    # ------------------------------------------------------------------
    # Game loop — corre indefinidamente hasta que el usuario cierre la ventana
    # ------------------------------------------------------------------
    while True:

        # Paso 1: vaciar la cola de eventos del SO.
        # Si no llamamos a event.get() en cada frame, el sistema operativo
        # interpreta que el programa está colgado y marca la ventana como
        # "(No responde)" después de unos segundos.
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                # pygame.quit() apaga los submódulos (libera recursos de audio,
                # display, etc.). sys.exit() termina el proceso Python.
                # Solo con pygame.quit() el proceso Python seguiría corriendo.
                pygame.quit()
                sys.exit()

        # Paso 2: medir el tiempo real de este frame.
        # La conversión /1000.0 es necesaria porque tick() devuelve milisegundos
        # y env.step() espera segundos. Un frame a 60 FPS = ~16.67 ms = ~0.01667 s.
        dt_ms = clock.tick(FPS)
        dt = dt_ms / 1000.0

        # Paso 3: gestión de pausa post-episodio.
        if waiting_reset:
            reset_timer += dt
            if reset_timer >= _RESET_DELAY_S:
                env.reset()
                waiting_reset = False
                reset_timer = 0.0
                # El nuevo episodio empieza con estado desconocido: reseteamos
                # a ceros para que la red no reciba valores del episodio anterior.
                current_state = np.zeros(14, dtype=np.float32)
            # Renderizamos el último frame durante la pausa para que la
            # pantalla no quede en negro; el jugador ve la posición final.
            env.render(surface)
            pygame.display.flip()
            continue   # saltamos el step normal hasta que se reinicie

        # Paso 4: construir acción — teclado en modo 'play', red en los demás.
        if genome is not None:
            # La red recibe el estado del frame anterior y devuelve (accel, brake).
            # genome.forward() retorna np.ndarray (2,); env.step() acepta cualquier
            # iterable de dos floats, así que no hace falta conversión explícita.
            action = genome.forward(current_state)
        else:
            keys = pygame.key.get_pressed()
            action = _build_action(keys)

        # Paso 5: avanzar la física un frame y capturar el nuevo estado.
        state, _reward, done, _info = env.step(action, dt)

        # Guardamos el estado para el próximo frame (solo lo usan los modos
        # con red neuronal, pero actualizarlo siempre no tiene costo apreciable).
        current_state = np.array(state, dtype=np.float32)

        # Paso 6: dibujar el frame sobre la surface
        env.render(surface)

        # Paso 7: intercambiar buffers → el frame recién dibujado aparece en pantalla
        pygame.display.flip()

        # Paso 8: si el episodio terminó, comenzar la pausa antes del reinicio
        if done:
            waiting_reset = True


if __name__ == "__main__":
    main()
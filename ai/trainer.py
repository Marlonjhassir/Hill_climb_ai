"""
ai/trainer.py — Orquestador del entrenamiento neuroevolutivo.

Responsabilidades:
  - Inicializar pygame en modo headless (sin ventana) para entrenamiento rápido.
  - Iterar generaciones: evaluar cada Genome en un episodio, asignar fitness,
    registrar métricas y llamar a GeneticAlgorithm.evolve().
  - Guardar checkpoints periódicos y reanudar desde el último guardado.
  - Exponer get_stats() para graficar la curva de evolución post-entrenamiento.

Prohibido: renderizar frames durante el entrenamiento, contener operadores
           evolutivos, o contener física de juego.
"""

import csv
import os
import pickle
from pathlib import Path

# SDL_VIDEODRIVER debe establecerse ANTES de que pygame se importe.
# El driver 'dummy' acepta todas las llamadas gráficas pero no abre ventana
# ni accede a GPU. Si se pone después del import, SDL ya leyó la variable
# al cargar la librería y el cambio no tiene efecto.
# setdefault no sobreescribe si la variable ya estaba definida, lo que
# permite que este módulo sea seguro de importar en otros contextos.
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame
import torch

from ai.genetic_algorithm import GeneticAlgorithm
from ai.genome import Genome
from config.settings import FPS, MODEL_DIR, SAVE_EVERY_N_GEN, STATS_DIR
from game.environment import Environment


class Trainer:
    """
    Orquesta el ciclo completo de entrenamiento neuroevolutivo.

    Cada generación:
      1. Todos los genomas juegan el mismo terreno (mismo seed = nº de generación).
      2. Se asigna fitness = max_distance + 50 * monedas_recogidas.
      3. GeneticAlgorithm.evolve() produce la siguiente generación.
      4. Se imprime un resumen, se guardan métricas en CSV y, cada
         SAVE_EVERY_N_GEN generaciones, se guarda un checkpoint completo.

    Al iniciarse, train() busca el checkpoint más reciente en MODEL_DIR.
    Si lo encuentra, lo carga y continúa desde donde se dejó; si no, arranca
    desde la generación 0.

    Args:
        n_generations: cuántas generaciones adicionales entrenar en esta
                       invocación (no el total absoluto). Si se reanuda desde
                       la gen 20 con n_generations=50, se corren las gens 20-69.

    Example:
        >>> trainer = Trainer(n_generations=5)
        >>> trainer.train()
        >>> stats = trainer.get_stats()
        >>> print(stats[0])  # {'gen': 0, 'best': ..., 'avg': ..., 'worst': ...}
    """

    # Paso de tiempo fijo para la simulación durante el entrenamiento.
    # Se deriva de FPS para que sea consistente con el juego manual.
    # Un dt fijo (a diferencia del variable de clock.tick()) garantiza que
    # dos episodios del mismo genoma producen resultados idénticos.
    _DT: float = 1.0 / FPS

    # Tope de seguridad de frames por episodio. El entorno devuelve done=True
    # cuando se acaba el tiempo, pero este límite protege contra bucles
    # infinitos si hubiera un bug que impidiera la condición de done.
    # 10 000 frames ≈ 167 segundos a 60 FPS, muy por encima del tiempo máximo
    # posible (20 s base + 5 checkpoints × 10 s = 70 s → 4 200 frames).
    _MAX_STEPS: int = 10_000

    def __init__(self, n_generations: int = 50) -> None:
        # pygame.init() es idempotente: si ya estaba inicializado no hace nada.
        pygame.init()

        self._n_generations: int = n_generations
        self._ga: GeneticAlgorithm = GeneticAlgorithm()

        # Una sola instancia de Environment reutilizada en todos los episodios.
        # reset(seed) reinicializa terreno y vehículo sin destruir los cuerpos
        # de pymunk, lo que es mucho más eficiente que crear un Environment nuevo
        # en cada evaluación.
        self._env: Environment = Environment(seed=0)

        # Métricas de la sesión actual. Cada elemento:
        # {'gen': int, 'best': float, 'avg': float, 'worst': float}
        # Nota: solo contiene las generaciones entrenadas en esta llamada a
        # train(); el historial completo vive en data/statistics/stats.csv.
        self._stats: list[dict] = []

        # Garantizar que los directorios de guardado existen antes de que
        # el loop de entrenamiento intente escribir en ellos.
        self._ensure_dirs()

    # ------------------------------------------------------------------
    # Bucle principal
    # ------------------------------------------------------------------

    def train(self) -> None:
        """
        Ejecuta el bucle de entrenamiento durante n_generations generaciones.

        Si existe un checkpoint previo en MODEL_DIR, lo carga y reanuda
        desde la siguiente generación. Si no, empieza desde la gen 0.

        Al terminar, get_stats() devuelve las métricas de esta sesión;
        el historial completo acumulado está en data/statistics/stats.csv.
        """
        loaded_population, start_gen = self._load_checkpoint()

        if loaded_population is not None:
            # Inyectamos la población cargada en el estado interno de
            # GeneticAlgorithm sin llamar a initialize(), porque initialize()
            # crearía pesos Kaiming nuevos que sobreescribirían los entrenados.
            # _population es privado, pero trainer.py es el único orquestador;
            # si se necesita encapsulación aquí se puede añadir load_population()
            # a GeneticAlgorithm en una futura refactorización.
            self._ga._population = loaded_population
            population = loaded_population
        else:
            population = self._ga.initialize()
            start_gen = 0

        end_gen = start_gen + self._n_generations
        print(
            f"Entrenamiento {'reanudado' if start_gen > 0 else 'iniciado'}: "
            f"generaciones {start_gen} – {end_gen - 1}, "
            f"{len(population)} individuos por generación.\n"
        )

        for gen in range(start_gen, end_gen):
            # Todos los individuos de esta generación enfrentan el mismo
            # terreno. La semilla es el número de generación: determinista
            # y reproducible sin necesidad de guardar estado del RNG.
            seed = gen

            for genome in population:
                self._run_episode(genome, seed)

            # Recolectamos métricas ANTES de evolve(), porque evolve()
            # resetea fitness a 0.0 en todos los individuos de la nueva gen.
            fitnesses = [g.fitness for g in population]
            stats = {
                'gen':   gen,
                'best':  max(fitnesses),
                'avg':   sum(fitnesses) / len(fitnesses),
                'worst': min(fitnesses),
            }
            self._stats.append(stats)
            self._log_generation(stats)

            # Guardamos una fila en CSV cada generación (registro continuo).
            self._save_stats_row(stats)

            # Checkpoint cada SAVE_EVERY_N_GEN generaciones completadas.
            # (gen + 1) % N == 0 en lugar de gen % N == 0 porque gen es
            # 0-indexado: si N=5, guardamos tras la 5ª gen (gen=4), 10ª (gen=9)...
            if (gen + 1) % SAVE_EVERY_N_GEN == 0:
                self._save_checkpoint(gen, population)

            population = self._ga.evolve()

        print("\nEntrenamiento completado.")

    # ------------------------------------------------------------------
    # Acceso a métricas
    # ------------------------------------------------------------------

    def get_stats(self) -> list[dict]:
        """
        Devuelve las métricas recopiladas en la sesión actual de train().

        Returns:
            Lista de dicts, uno por generación completada en esta sesión:
                'gen'   (int)   — número de generación (0-indexado, absoluto).
                'best'  (float) — fitness del mejor individuo.
                'avg'   (float) — fitness promedio de la población.
                'worst' (float) — fitness del peor individuo.
            Vacía si train() aún no fue llamado.
        """
        return self._stats

    # ------------------------------------------------------------------
    # Persistencia — escritura
    # ------------------------------------------------------------------

    def _ensure_dirs(self) -> None:
        """
        Crea MODEL_DIR y STATS_DIR si no existen.

        parents=True: crea directorios intermedios (p. ej. 'data/' si falta).
        exist_ok=True: no lanza error si el directorio ya existe.
        """
        Path(MODEL_DIR).mkdir(parents=True, exist_ok=True)
        Path(STATS_DIR).mkdir(parents=True, exist_ok=True)

    def _save_checkpoint(self, gen: int, population: list[Genome]) -> None:
        """
        Guarda la población completa y el mejor genoma en disco.

        Usa escritura atómica para ambos archivos: primero escribe a un
        archivo temporal (.tmp) y luego llama a os.replace(), que es una
        operación atómica del sistema operativo. Esto garantiza que si el
        proceso muere a mitad de escritura, el archivo anterior permanece
        intacto (nunca queda en estado corrupto intermedio).

        Formato de population_gen_N.pkl:
            list[dict] donde cada dict es {'weights': np.ndarray, 'fitness': float}.
            Se evita picklear el objeto Genome completo (que incluye módulos
            torch) porque atamos el archivo a la definición exacta de clase;
            si PolicyNet cambia, el archivo se vuelve irrecuperable.

        Formato de best_genome.pt:
            dict {'weights': torch.Tensor, 'fitness': float, 'generation': int}.
            torch.save es la convención estándar para checkpoints de PyTorch.

        Args:
            gen: número de generación recién completada.
            population: lista de Genome con fitness asignado.
        """
        model_path = Path(MODEL_DIR)

        # --- Población completa ---
        pop_data = [
            {'weights': g.get_weights(), 'fitness': g.fitness}
            for g in population
        ]
        pop_file = model_path / f"population_gen_{gen}.pkl"
        pop_tmp  = model_path / f"population_gen_{gen}.pkl.tmp"

        with open(pop_tmp, 'wb') as f:
            pickle.dump(pop_data, f)

        # os.replace mueve el .tmp al nombre final de forma atómica.
        # En Windows y Linux, si el proceso muere antes de este punto,
        # pop_file (el checkpoint anterior) no se toca.
        os.replace(pop_tmp, pop_file)

        # --- Mejor genoma ---
        best = max(population, key=lambda g: g.fitness)
        best_data = {
            'weights':    torch.tensor(best.get_weights(), dtype=torch.float32),
            'fitness':    best.fitness,
            'generation': gen,
        }
        best_file = model_path / "best_genome.pt"
        best_tmp  = model_path / "best_genome.pt.tmp"

        torch.save(best_data, best_tmp)
        os.replace(best_tmp, best_file)

        print(f"  [checkpoint] Guardado gen {gen} → {pop_file.name} + best_genome.pt")

    def _save_stats_row(self, stats: dict) -> None:
        """
        Añade una fila al CSV de métricas históricas.

        Abre el archivo en modo 'append' para no sobreescribir generaciones
        anteriores. Escribe la cabecera solo si el archivo es nuevo o vacío.

        Args:
            stats: dict con claves 'gen', 'best', 'avg', 'worst'.
        """
        csv_path = Path(STATS_DIR) / "stats.csv"

        # Verificamos ANTES de abrir el archivo porque open('a') lo crea vacío
        # si no existe, haciendo que exists() devuelva True inmediatamente.
        # stat().st_size == 0 cubre el caso de archivo creado pero sin contenido.
        is_new = not csv_path.exists() or csv_path.stat().st_size == 0

        with open(csv_path, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['gen', 'best', 'avg', 'worst'])
            if is_new:
                writer.writeheader()
            writer.writerow(stats)

    # ------------------------------------------------------------------
    # Persistencia — lectura
    # ------------------------------------------------------------------

    def _load_checkpoint(self) -> tuple[list[Genome] | None, int]:
        """
        Busca el checkpoint más reciente y lo carga.

        Proceso:
          1. Escanea MODEL_DIR buscando archivos population_gen_N.pkl.
          2. Toma el de mayor N (el más reciente).
          3. Reconstruye la lista de Genome: crea Genome(), inyecta pesos y
             fitness. Reconstruir desde datos planos (no picklear Genome)
             hace que el formato sea robusto ante cambios en PolicyNet.
          4. Si el archivo no existe o está corrupto, avisa y devuelve None
             para que train() arranque limpio.

        Returns:
            (population, start_gen) si se cargó correctamente,
            (None, 0) si no hay checkpoint o falló la carga.
        """
        latest_gen = self._latest_checkpoint_gen()
        if latest_gen < 0:
            print("  [checkpoint] Sin guardado previo. Arrancando desde generación 0.")
            return None, 0

        pop_file = Path(MODEL_DIR) / f"population_gen_{latest_gen}.pkl"
        try:
            with open(pop_file, 'rb') as f:
                pop_data: list[dict] = pickle.load(f)

            population: list[Genome] = []
            for item in pop_data:
                g = Genome()
                g.set_weights(item['weights'])  # inyecta los pesos entrenados
                g.fitness = item['fitness']
                population.append(g)

            start_gen = latest_gen + 1
            print(
                f"  [checkpoint] Reanudando desde generación {start_gen} "
                f"(cargado: {pop_file.name}, {len(population)} individuos)."
            )
            return population, start_gen

        except Exception as e:
            # Un archivo corrupto no debe detener el entrenamiento.
            # Reportamos el problema y arrancamos con población aleatoria.
            print(f"  [checkpoint] ADVERTENCIA: no se pudo cargar {pop_file.name}: {e}")
            print(f"  [checkpoint] Arrancando desde generación 0.")
            return None, 0

    def _latest_checkpoint_gen(self) -> int:
        """
        Encuentra el número de generación más alto entre los checkpoints guardados.

        Escanea MODEL_DIR buscando archivos con el patrón population_gen_N.pkl
        y extrae el N más grande. El patrón glob excluye los .pkl.tmp que
        quedarían de una escritura interrumpida, porque *.pkl no los captura.

        Returns:
            El N más alto encontrado, o -1 si no hay ningún checkpoint.
        """
        model_path = Path(MODEL_DIR)
        if not model_path.exists():
            return -1

        gens: list[int] = []
        for f in model_path.glob("population_gen_*.pkl"):
            try:
                # f.stem de "population_gen_42.pkl" → "population_gen_42"
                # split("_")[-1] → "42"
                n = int(f.stem.split("_")[-1])
                gens.append(n)
            except ValueError:
                pass  # archivo con nombre inesperado: ignorar sin crashear

        return max(gens) if gens else -1

    # ------------------------------------------------------------------
    # Evaluación de episodios
    # ------------------------------------------------------------------

    def _run_episode(self, genome: Genome, seed: int) -> None:
        """
        Ejecuta un episodio completo y asigna fitness al genoma.

        El episodio termina cuando el entorno devuelve done=True (el jugador
        toca el suelo o se acaba el tiempo) o al alcanzar _MAX_STEPS.
        No se llama a env.render(): el entrenamiento es completamente headless.

        Args:
            genome: individuo a evaluar. genome.fitness se escribe in-place.
            seed:   semilla del terreno para este episodio.
        """
        self._env.reset(seed=seed)

        # Estado inicial antes del primer step: el vehículo acaba de aparecer,
        # no ha recibido ninguna acción todavía.
        state = self._env.get_state()

        for _ in range(self._MAX_STEPS):
            action = genome.forward(state)

            # step() devuelve el estado TRAS aplicar la acción; lo reutilizamos
            # en el siguiente frame sin llamar a get_state() de nuevo.
            state, _, done, _ = self._env.step(action, self._DT)

            if done:
                break

        # Fórmula de fitness del plan maestro (sección 7.4 de CLAUDE.md):
        # distancia_maxima + 50 * monedas_recogidas.
        # env.score cuenta monedas con COIN_VALUE=1, así que es el conteo directo.
        genome.fitness = self._env.max_distance + 50.0 * self._env.score

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log_generation(self, stats: dict) -> None:
        """
        Imprime en consola el resumen de la generación.

        Args:
            stats: dict con claves 'gen', 'best', 'avg', 'worst'.
        """
        print(
            f"Gen {stats['gen']:>3} | "
            f"mejor: {stats['best']:>8.1f} | "
            f"promedio: {stats['avg']:>8.1f} | "
            f"peor: {stats['worst']:>8.1f}"
        )
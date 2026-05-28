"""
ai/genetic_algorithm.py — Operadores evolutivos del algoritmo genético.

Responsabilidades:
  - Crear la población inicial de Genomes.
  - Implementar selección por torneo, crossover uniforme y elitismo.
  - Producir la siguiente generación a partir de la población evaluada.

Prohibido: evaluar individuos, correr episodios, o contener lógica de juego.
           Eso es responsabilidad de trainer.py.
"""

import random

import numpy as np

from ai.genome import Genome
from config.settings import (
    CROSSOVER_RATE,
    ELITISM_COUNT,
    POPULATION_SIZE,
    TOURNAMENT_SIZE,
)


class GeneticAlgorithm:
    """
    Implementa el ciclo evolutivo sobre una población de Genomes.

    Uso típico desde trainer.py:
        ga = GeneticAlgorithm()
        population = ga.initialize()

        for generacion in range(N_GENERATIONS):
            for genome in ga.get_population():
                genome.fitness = evaluar_episodio(genome)
            ga.evolve()

    Flujo de evolve():
        1. Ordenar población por fitness descendente.
        2. Copiar los ELITISM_COUNT mejores sin modificar (elitismo).
        3. Completar la población con hijos generados por torneo + crossover + mutación.
    """

    def __init__(self) -> None:
        # La población se inicializa vacía; debe llamarse initialize() antes de evolve().
        self._population: list[Genome] = []

    # ------------------------------------------------------------------
    # Creación de la población inicial
    # ------------------------------------------------------------------

    def initialize(self) -> list[Genome]:
        """
        Crea POPULATION_SIZE genomas con pesos Kaiming aleatorios.

        Se llama una sola vez al inicio del entrenamiento (o se reemplaza
        por load() en Fase 7 si se retoma desde un checkpoint).

        Returns:
            Lista de Genome recién creados, con fitness=0.0.
        """
        self._population = [Genome() for _ in range(POPULATION_SIZE)]
        return self._population

    # ------------------------------------------------------------------
    # Acceso a la población
    # ------------------------------------------------------------------

    def get_population(self) -> list[Genome]:
        """
        Devuelve referencia a la población actual.

        trainer.py la itera para asignar fitness después de cada episodio.
        Es una referencia, no una copia: modificar los Genome del exterior
        afecta el estado interno de GeneticAlgorithm (comportamiento deseado).

        Returns:
            Lista de Genome con sus fitness del episodio anterior (o 0.0 si
            es la primera generación).
        """
        return self._population

    # ------------------------------------------------------------------
    # Ciclo evolutivo principal
    # ------------------------------------------------------------------

    def evolve(self) -> list[Genome]:
        """
        Produce la siguiente generación a partir de la población evaluada.

        Precondición: todos los Genome en self._population tienen fitness
        asignado por trainer.py. Si alguno tiene fitness=0.0 porque no fue
        evaluado, participará con desventaja en la selección (comportamiento
        correcto: indica que el individuo no avanzó nada).

        Returns:
            Nueva lista de Genome (reemplaza self._population internamente).
            fitness=0.0 en todos para que trainer.py los re-evalúe.
        """
        # Ordenar de mayor a menor fitness para identificar la élite.
        # sorted() es estable y no modifica self._population en el proceso.
        sorted_pop = sorted(
            self._population, key=lambda g: g.fitness, reverse=True
        )

        next_gen: list[Genome] = []

        # ------------------------------------------------------------------
        # Elitismo: los mejores pasan sin modificar a la siguiente generación.
        # Usamos copy() para que trainer.py pueda mutar / evaluar los
        # originales sin afectar a los herederos.
        # El fitness se resetea porque serán re-evaluados en la nueva generación
        # con una semilla de terreno distinta (regla 7.5 del plan maestro).
        # ------------------------------------------------------------------
        for genome in sorted_pop[:ELITISM_COUNT]:
            elite = genome.copy()
            elite.fitness = 0.0
            next_gen.append(elite)

        # ------------------------------------------------------------------
        # Descendencia: completar la población con hijos.
        # Cada hijo se obtiene seleccionando dos padres por torneo,
        # cruzándolos y mutando el resultado.
        # ------------------------------------------------------------------
        while len(next_gen) < POPULATION_SIZE:
            parent_a = self._tournament_select()
            parent_b = self._tournament_select()
            child = self._crossover(parent_a, parent_b)
            child.mutate()
            next_gen.append(child)

        self._population = next_gen
        return self._population

    # ------------------------------------------------------------------
    # Métodos privados
    # ------------------------------------------------------------------

    def _tournament_select(self) -> Genome:
        """
        Selecciona un individuo por torneo de tamaño TOURNAMENT_SIZE.

        Elige TOURNAMENT_SIZE candidatos al azar de la población y devuelve
        el de mayor fitness. Esta presión selectiva es moderada: los buenos
        tienen más probabilidad de ganar, pero no dominan completamente.

        Por qué torneo y no ruleta (proporcional al fitness):
            Si un individuo tiene fitness 1000 y los demás tienen 1, la ruleta
            le da el 99.9% de la descendencia → la diversidad colapsa en 2-3
            generaciones. El torneo limita ese dominio de forma natural.

        Returns:
            El Genome con mayor fitness entre los candidatos sorteados.
        """
        # random.sample garantiza candidatos sin repetición: un individuo
        # no puede competir consigo mismo en el mismo torneo.
        # min() protege contra TOURNAMENT_SIZE > len(población), aunque con
        # los valores de settings.py (3 vs 50) nunca debería ocurrir.
        k = min(TOURNAMENT_SIZE, len(self._population))
        candidates = random.sample(self._population, k)
        return max(candidates, key=lambda g: g.fitness)

    def _crossover(self, parent_a: Genome, parent_b: Genome) -> Genome:
        """
        Aplica crossover uniforme entre dos padres y devuelve un hijo nuevo.

        Con probabilidad CROSSOVER_RATE se mezclan los pesos de ambos padres
        gen a gen (50% de cada uno). De lo contrario, el hijo es copia de
        parent_a. En ambos casos el hijo tiene fitness=0.0.

        Por qué empezar desde copy(parent_a) y no desde Genome():
            Genome() inicializa pesos con Kaiming y luego set_weights()
            los sobreescribe → dos inicializaciones de 470 pesos.
            copy() hace una sola copia profunda → más eficiente.

        Args:
            parent_a: primer padre (seleccionado por torneo).
            parent_b: segundo padre (seleccionado por torneo).

        Returns:
            Genome hijo con fitness=0.0, listo para ser evaluado.
        """
        # Partimos de una copia de parent_a; si no hay crossover, ya está.
        child = parent_a.copy()
        child.fitness = 0.0

        if random.random() < CROSSOVER_RATE:
            w_a = parent_a.get_weights()  # array (470,) float32
            w_b = parent_b.get_weights()  # array (470,) float32

            # Máscara booleana: True → tomar peso de w_a, False → de w_b.
            # np.random.rand(n) genera n valores uniformes en [0, 1);
            # comparar con 0.5 produce True en ~50% de las posiciones.
            mask = np.random.rand(len(w_a)) < 0.5

            # np.where(condición, valor_si_true, valor_si_false)
            # Elemento a elemento: child[i] = w_a[i] si mask[i] else w_b[i].
            child.set_weights(np.where(mask, w_a, w_b))

        return child
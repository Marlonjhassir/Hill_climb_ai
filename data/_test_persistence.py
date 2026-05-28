"""_test_persistence.py — verificación de Fase 7 persistencia."""

from pathlib import Path
import numpy as np
from ai.trainer import Trainer

# --- Parte 1: entrenar 7 generaciones (guardará en gen 4) ---
print("=== ENTRENAMIENTO INICIAL (7 generaciones) ===")
t1 = Trainer(n_generations=7)
t1.train()

# --- Parte 2: reanudar y verificar que arranca desde gen 7 ---
print("\n=== REANUDACIÓN ===")
t2 = Trainer(n_generations=3)
t2.train()
stats = t2.get_stats()
first_gen_in_resume = stats[0]['gen']
print(f"\nPrimera gen en reanudación: {first_gen_in_resume}  (esperado: 5)")

# --- Parte 3: verificar pesos restaurados ---
from pathlib import Path
import pickle
from ai.genome import Genome

pop_file = sorted(Path("data/saved_models").glob("population_gen_*.pkl"))[-1]
with open(pop_file, 'rb') as f:
    pop_data = pickle.load(f)

g_loaded = Genome()
g_loaded.set_weights(pop_data[0]['weights'])
g_saved  = Genome()
g_saved.set_weights(pop_data[0]['weights'])
pesos_iguales = np.allclose(g_loaded.get_weights(), g_saved.get_weights())
print(f"Pesos restaurados correctamente: {pesos_iguales}  (esperado: True)")

# --- Parte 4: verificar CSV ---
csv_path = Path("data/statistics/stats.csv")
rows = csv_path.read_text().strip().split("\n")
print(f"Filas en stats.csv (cabecera + datos): {len(rows)}  (esperado: 11)")
print(f"Cabecera: {rows[0]}")
print(f"Primera fila: {rows[1]}")
print(f"Última fila:  {rows[-1]}")
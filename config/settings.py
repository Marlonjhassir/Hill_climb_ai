# === Ventana y rendering ===
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
FPS = 60

# === Fisica ===
GRAVITY = 900               # px/s^2
WHEEL_FRICTION = 1.5
CHASSIS_MASS = 5.0
WHEEL_MASS = 1.0

# === Episodio ===
MAX_TIME = 20.0         # segundos sin checkpoint-> muerte
CHECKPOINT_TIME = 10.0  # segundos que anade un checkpoint
TARGET_DISTANCE = 100   # px minimos para considerar avance

# === Red neuronal ===
NN_INPUTS = 14
NN_HIDDEN = [16, 12]
NN_OUTPUTS = 2
LOOKAHEAD_DISTANCES = [30, 80, 150, 250] # px frente al vehiculo

# === Algoritmo genetico ===
POPULATION_SIZE = 50
ELITISM_COUNT = 3       # mejores individuos que pasan sin mutar
MUTATION_RATE = 0.1     # probabilidad por peso
MUTATION_SIGMA = 0.2    # desviacion estandar del ruido gaussiano
TOURNAMENT_SIZE = 3
CROSSOVER_RATE = 0.7

# === Persistencia ===
SAVE_EVERY_N_GEN = 5
MODEL_DIR = "data/saved_models"
STATS_DIR = "data/statistics"
import sys
import os

# Agrega el directorio actual al sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scraping import ScrapingService

if __name__ == "__main__":
    servicio_scraping = ScrapingService()
    archivo_entrada = 'cedulas_entrada.xlsx'
    archivo_salida = 'resultados_salida.xlsx'
    servicio_scraping.procesar_masivo_desde_excel(archivo_entrada, archivo_salida)

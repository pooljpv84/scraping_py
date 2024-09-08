import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import config
import base64
import openai
import urllib3
from webdriver_manager.firefox import GeckoDriverManager
import pandas as pd
import sys
import os

urllib3.disable_warnings()
base_dir = os.path.dirname(os.path.abspath(__file__))
path_general = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ScrapingService:
    def __init__(self):
        firefox_options = FirefoxOptions()
        firefox_options.profile = webdriver.FirefoxProfile()
        firefox_options.add_argument("--no-sandbox")
        firefox_options.add_argument("--disable-dev-shm-usage")
        firefox_options.add_argument("--disable-gpu")
        firefox_options.set_preference("media.navigator.enabled", False)
        firefox_options.set_preference("media.peerconnection.enabled", False)
        firefox_options.set_preference("webgl.disabled", True)
        firefox_options.set_preference("dom.webnotifications.enabled", False)
        firefox_options.log.level = "trace"

        # Si queres ejecutar en segundo plano
        # firefox_options.add_argument("--headless")

        service = FirefoxService(config.FIREFOX_DRIVER_PATH, log_path="selenium_log.log")
        self.driver = webdriver.Firefox(service=service, options=firefox_options)

        # call constant
        openai.api_key = config.API_OPENAI

    def resolver_captcha_gpt_vision(self, captcha_image_path):
        print("-> Resolviendo el captcha con GPT-4 Vision")
        base64_image = self.encode_image(captcha_image_path)

        if base64_image is None:
            print("Error: No se pudo convertir la imagen a base64.")
            return None

        try:
            response = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Resuelve el texto de la imagen del captcha. Devuelve únicamente el texto sin ningún otro comentario. Si no puedes identificar claramente el texto, devuelve 'NO'. Asegúrate de distinguir entre mayúsculas y minúsculas. Intenta interpretar cualquier distorsión en los caracteres de la imagen."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=200
            )
            return response['choices'][0]['message']['content']
        except Exception as e:
            print(f"Error durante la solicitud a OpenAI: {e}")
            return None

    def encode_image(self, image_path):
        """Image to base64 oo si"""
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode("utf-8")
        except Exception as e:
            print(f"Error al leer la imagen: {e}")
            return None

    def obtener_informacion_educativa(self, cedula):
        """Realizar el scraping para obtener la información educativa de una cédula."""
        try:
            print(f"-> Accediendo a la página con la cédula: {cedula}")
            self.driver.get(config.URL)

            print("-> Ingresando la cédula en el formulario")
            cedula_input = self.driver.find_element(By.ID, 'formBusqueda:cedula')
            cedula_input.send_keys(str(cedula))

            max_reintentos = 5
            for intento in range(max_reintentos):
                print(f"-> Intento {intento + 1} de {max_reintentos}")
                captcha_img = self.driver.find_element(By.ID, 'formBusqueda:capimg')
                captcha_img.screenshot('captcha.png')
                print("-> Imagen del captcha guardada como 'captcha.png'")

                captcha_resuelto = self.resolver_captcha_gpt_vision(os.path.join(path_general, 'captcha.png'))

                if captcha_resuelto != "NO":
                    print("-> Ingresando el captcha resuelto en el formulario")
                    captcha_input = self.driver.find_element(By.ID, 'formBusqueda:captcha')
                    captcha_input.send_keys(captcha_resuelto)

                    print("-> Haciendo clic en el botón de 'Consultar'")
                    consultar_button = self.driver.find_element(By.ID, 'formBusqueda:clBuscar')
                    consultar_button.click()

                    time.sleep(5)

                    try:
                        mensaje_error = self.driver.find_element(By.ID, 'formBusqueda:validarCaptcha').text
                        if "El captcha ingresado es incorrecto" in mensaje_error:
                            print("-> Captcha incorrecto, generando uno nuevo y reintentando...")
                            continue
                    except:
                        pass

                    print("-> Esperando a que la tabla esté visible")
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".rf-dt"))
                    )

                    print("-> Extrayendo la tabla de resultados")
                    tabla = self.driver.find_element(By.CSS_SELECTOR, ".rf-dt")
                    filas = tabla.find_elements(By.TAG_NAME, "tr")

                    resultados = []
                    for fila in filas[1:]:
                        columnas = fila.find_elements(By.TAG_NAME, "td")
                        fila_datos = [columna.text for columna in columnas]
                        # Verifica que la fila no tenga símbolos decorativos antes de agregarla
                        if "«««««««" not in fila_datos[0]:
                            resultados.append(fila_datos)

                    print(f"-> Resultados extraídos: {resultados}")

                    # Retornar siempre 9 columnas (llenando con 0s en caso de que falten datos)
                    if resultados:
                        return resultados[0] + [0] * (9 - len(resultados[0]))
                    else:
                        return None

                else:
                    print(f"-> Captcha no resuelto en el intento {intento + 1}")

            return None
        finally:
            print("-> Cerrando el navegador...")
            # self.driver.quit() Cerrar el driver del browser

    def procesar_masivo_desde_excel(self, archivo_entrada, archivo_salida):
        # Leer las cédulas desde el archivo Excel asegurándose de que sean tratadas como texto
        df = pd.read_excel(archivo_entrada, dtype={'Cedula': str})  # Especifica que la columna Cedula es de tipo texto
        cedulas = df['Cedula']

        resultados = []

        # Recorrer las cédulas y obtener los resultados
        for cedula in cedulas:
            print(f"Procesando cédula: {cedula}")
            resultado = self.obtener_informacion_educativa(cedula)

            # Si hay un resultado, lo agregamos; si no, agregamos la cédula con ceros
            if resultado:
                # Si el resultado contiene "No existe registro", lo manejamos con ceros
                if "No existe registro" in resultado[0]:
                    print(f"No hay registro de título para la cédula {cedula}")
                    resultados.append([0, cedula, 0, 0, 0, 0, 0, 0, 0])  # Agregamos la cédula con los valores '0'
                else:
                    resultados.append(resultado)
            else:
                # En caso de none tb poner 0's
                resultados.append([0, cedula, 0, 0, 0, 0, 0, 0, 0])

        # Crear un nuevo DataFrame con los resultados y guardarlo en un archivo Excel
        columnas = ['Nº', 'Cédula', 'Nombre', 'Institución', 'Título', 'Especialidad', 'Fecha Grado', 'Refrendación',
                    'Acción']
        df_resultados = pd.DataFrame(resultados, columns=columnas)

        df_resultados.to_excel(archivo_salida, index=False)
        print(f"Resultados guardados en {archivo_salida}")


# Main block ,,
if __name__ == "__main__":
    servicio_scraping = ScrapingService()
    archivo_entrada = os.path.join(base_dir, 'cedulas_entrada.xlsx')
    archivo_salida = os.path.join(base_dir, 'cedulas_salida.xlsx')
    servicio_scraping.procesar_masivo_desde_excel(archivo_entrada, archivo_salida)

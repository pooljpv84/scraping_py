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
        firefox_options.binary_location = r'C:\Program Files\Mozilla Firefox\firefox.exe'

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
            return "NO"

        # model="gpt-4o-mini",
        # model= "gpt-4-vision-preview",
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Lee el captcha del PNG adjunto y devuelve SOLAMENTE el texto del captcha. Si no es legible, responde exactamente 'NO'. Respeta mayúsculas/minúsculas."
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
                max_tokens=20
            )
            raw = response['choices'][0]['message']['content'] if response else "NO"
            if not isinstance(raw, str):
                return "NO"
            texto = raw.strip().splitlines()[0] if raw else ""
            # Sanitizar: mantener solo caracteres típicos de captcha alfanuméricos
            try:
                import re
                texto = re.sub(r"[^A-Za-z0-9]", "", texto)
            except Exception:
                pass
            if not texto:
                return "NO"
            return texto
        except Exception as e:
            print(f"Error durante la solicitud a OpenAI: {e}")
            return "NO"

    def encode_image(self, image_path):
        """Image to base64 oo si"""
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode("utf-8")
        except Exception as e:
            print(f"Error al leer la imagen: {e}")
            return None

    def preparar_formulario(self, cedula):
        """Selecciona la búsqueda por cédula y vuelve a escribirla tras cada carga."""
        from selenium.common.exceptions import StaleElementReferenceException

        print("-> Seleccionando el tipo de búsqueda (radio)")
        for intento in range(5):
            try:
                radio = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.ID, 'formBusqueda:selecItem:0'))
                )
                if not radio.is_selected():
                    try:
                        radio.click()
                    except Exception:
                        self.driver.execute_script("arguments[0].click();", radio)

                print("-> Esperando 5 segundos antes de ingresar la cédula")
                time.sleep(5)

                cedula_input = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.ID, 'formBusqueda:cedula'))
                )
                cedula_input.clear()
                cedula_input.send_keys(str(cedula))
                print(f"-> Cédula reingresada: {cedula}")
                return
            except StaleElementReferenceException:
                time.sleep(0.3)
            except Exception as e:
                if intento == 4:
                    raise RuntimeError(
                        f"No se pudo preparar el formulario para la cédula {cedula}"
                    ) from e
                time.sleep(0.5)

    def captcha_incorrecto(self):
        """Indica si el sitio mostró el mensaje de captcha rechazado."""
        try:
            mensaje = self.driver.find_element(
                By.ID, 'formBusqueda:validarCaptcha'
            ).text
            return "captcha ingresado es incorrecto" in mensaje.lower()
        except Exception:
            return False

    def cedula_sin_informacion(self):
        """Detecta que la cédula no tiene títulos registrados."""
        mensaje_esperado = (
            "no consta información de títulos de bachiller "
            "registrados en el sistema"
        )
        try:
            elementos = self.driver.find_elements(
                By.XPATH,
                "//div[contains(@class,'table-responsive')]"
                "//span[contains(translate(normalize-space(.),"
                "'ABCDEFGHIJKLMNOPQRSTUVWXYZÁÉÍÓÚÜÑ',"
                "'abcdefghijklmnopqrstuvwxyzáéíóúüñ'),"
                "'no consta información de títulos de bachiller registrados en el sistema')]"
            )
            if elementos:
                return True

            texto_pagina = self.driver.find_element(By.TAG_NAME, "body").text.lower()
            return mensaje_esperado in texto_pagina
        except Exception:
            return False

    def esperar_resultado_consulta(self, timeout=12):
        """Espera uno de los posibles resultados posteriores a Consultar."""
        fin = time.time() + timeout
        xpath_ver_informacion = (
            "//input[starts-with(@id,'formBusqueda:j_idt') "
            "and @type='submit' "
            "and normalize-space(@value)='Ver información']"
        )

        while time.time() < fin:
            if self.captcha_incorrecto():
                return "captcha_incorrecto"
            if self.cedula_sin_informacion():
                return "sin_informacion"
            if self.driver.find_elements(By.XPATH, xpath_ver_informacion):
                return "con_informacion"
            time.sleep(0.3)

        return "sin_respuesta"

    def recargar_para_nuevo_captcha(self, cedula):
        """Recarga, reingresa la cédula y deja listo un captcha nuevo."""
        self.driver.refresh()
        self.preparar_formulario(cedula)

    def obtener_informacion_educativa(self, cedula):
        """Realizar el scraping para obtener la información educativa de una cédula."""
        try:
            print(f"-> Accediendo a la página con la cédula: {cedula}")
            self.driver.get(config.URL)
            self.preparar_formulario(cedula)

            max_reintentos = 5
            for intento in range(max_reintentos):
                # Se conserva en Python aunque la página se recargue.
                nombre_persona = 0
                print(f"-> Intento {intento + 1} de {max_reintentos}")
                captcha_path = os.path.join(path_general, 'captcha.png')
                try:
                    if os.path.exists(captcha_path):
                        os.remove(captcha_path)
                except Exception as e:
                    print(f"Advertencia: no se pudo eliminar el captcha anterior: {e}")

                # Capturar el captcha con espera y reintentos para evitar StaleElementReferenceException
                from selenium.common.exceptions import StaleElementReferenceException
                captcha_capturado = False
                for intento_capimg in range(5):
                    try:
                        captcha_img = WebDriverWait(self.driver, 10).until(
                            EC.presence_of_element_located((By.ID, 'formBusqueda:capimg'))
                        )
                        try:
                            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", captcha_img)
                        except Exception:
                            pass
                        # Esperar a que la imagen esté completamente cargada
                        try:
                            WebDriverWait(self.driver, 5).until(
                                lambda d: d.execute_script(
                                    "var i=arguments[0]; return i && i.complete && i.naturalWidth>0;",
                                    captcha_img
                                )
                            )
                        except Exception:
                            pass
                        captcha_img.screenshot(captcha_path)
                        print(f"-> Imagen del captcha guardada en '{captcha_path}'")
                        captcha_capturado = True
                        break
                    except StaleElementReferenceException:
                        time.sleep(0.3)
                        continue
                    except Exception as e:
                        if intento_capimg == 4:
                            print(f"Advertencia: no se pudo capturar el captcha: {e}")
                        time.sleep(0.3)
                        continue

                if not captcha_capturado:
                    # No se pudo capturar la imagen del captcha; pasar al siguiente intento del bucle principal
                    continue

                captcha_resuelto = self.resolver_captcha_gpt_vision(captcha_path)

                # Validar respuesta del solver. Debe ser string no vacío y distinto de 'NO'
                if isinstance(captcha_resuelto, str):
                    captcha_resuelto = captcha_resuelto.strip()
                else:
                    captcha_resuelto = ""

                if captcha_resuelto and captcha_resuelto != "NO":
                    print("-> Ingresando el captcha resuelto en el formulario")
                    # Enfocar el input del captcha antes de escribir
                    intentos_captcha = 3
                    for intento_cap in range(intentos_captcha):
                        try:
                            captcha_input = WebDriverWait(self.driver, 10).until(
                                EC.element_to_be_clickable((By.ID, 'formBusqueda:captcha'))
                            )
                            try:
                                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", captcha_input)
                            except Exception:
                                pass
                            try:
                                captcha_input.click()
                            except Exception:
                                # Fallback con JavaScript por si el click normal falla
                                self.driver.execute_script("arguments[0].click();", captcha_input)
                            try:
                                captcha_input.clear()
                            except Exception:
                                pass
                            captcha_input.send_keys(captcha_resuelto)
                            break
                        except Exception as e:
                            from selenium.common.exceptions import StaleElementReferenceException
                            if isinstance(e, StaleElementReferenceException) and intento_cap < intentos_captcha - 1:
                                time.sleep(0.3)
                                continue
                            else:
                                print(f"Advertencia: no se pudo escribir el captcha en el intento {intento_cap+1}: {e}")
                                break

                    print("-> Haciendo clic en el botón de 'Consultar'")
                    time.sleep(2)
                    consultar_button = self.driver.find_element(By.ID, 'formBusqueda:clBuscar')
                    consultar_button.click()

                    resultado_consulta = self.esperar_resultado_consulta()

                    if resultado_consulta == "captcha_incorrecto":
                        print(
                            "-> Captcha incorrecto. Recargando la página y "
                            "capturando uno nuevo con la misma cédula..."
                        )
                        self.recargar_para_nuevo_captcha(cedula)
                        continue

                    if resultado_consulta == "sin_informacion":
                        print(
                            "-> La cédula no consta con títulos registrados. "
                            "Se guardará con valores en cero."
                        )
                        return None

                    if resultado_consulta == "sin_respuesta":
                        print(
                            "-> La consulta no produjo un resultado reconocible. "
                            "Recargando para intentar con un captcha nuevo."
                        )
                        self.recargar_para_nuevo_captcha(cedula)
                        continue

                    # Extraer 'Nombres' del bloque INFORMACIÓN PERSONAL, si está disponible
                    try:
                        print("-> Esperando y extrayendo 'Nombres' en INFORMACIÓN PERSONAL")
                        cont_info = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.ID, 'formBusqueda:infoPersonal'))
                        )
                        # Buscar el primer/único table dentro del span
                        tabla_info = cont_info.find_element(By.TAG_NAME, 'table')
                        filas_info = tabla_info.find_elements(By.TAG_NAME, 'tr')
                        for fila in filas_info:
                            celdas = fila.find_elements(By.TAG_NAME, 'td')
                            if len(celdas) >= 2:
                                etiqueta = celdas[0].text.strip().upper()
                                valor = celdas[1].text.strip()
                                if 'NOMBRES' in etiqueta and valor:
                                    nombre_persona = valor
                                    print(f"-> Nombres extraídos: {nombre_persona}")
                                    break
                    except Exception as e:
                        print(f"Advertencia: no se pudo extraer 'Nombres': {e}")

                    xpath_btn = "//input[starts-with(@id,'formBusqueda:j_idt') and @type='submit' and normalize-space(@value)='Ver información']"
                    clicked_ver_info = False
                    try:
                        print("-> Esperando el botón 'Ver información'")
                        boton_ver_info = WebDriverWait(self.driver, 12).until(
                            EC.element_to_be_clickable((By.XPATH, xpath_btn))
                        )
                        try:
                            boton_ver_info.click()
                        except Exception:
                            self.driver.execute_script(
                                "arguments[0].click();", boton_ver_info
                            )
                        clicked_ver_info = True
                        print("-> Clic en 'Ver información' realizado")
                        time.sleep(1)
                    except Exception as e:
                        print(f"-> No apareció 'Ver información': {e}")

                    if not clicked_ver_info:
                        print(
                            "-> Reiniciando la página con la misma cédula "
                            "para intentar nuevamente."
                        )
                        self.recargar_para_nuevo_captcha(cedula)
                        continue

                    print("-> Esperando a que la sección de tabla 'formBusqueda:tabla' esté visible")
                    contenedor_tabla = WebDriverWait(self.driver, 15).until(
                        EC.presence_of_element_located((By.ID, 'formBusqueda:tabla'))
                    )

                    # Esperar a que se renderice la tabla dentro del contenedor (RichFaces puede tardar)
                    tabla = None
                    end_time = time.time() + 12
                    while time.time() < end_time and tabla is None:
                        try:
                            # Buscar primero por clase rf-dt
                            posibles = contenedor_tabla.find_elements(By.CSS_SELECTOR, "table.rf-dt")
                            if not posibles:
                                # Fallback: cualquier tabla dentro del contenedor
                                posibles = contenedor_tabla.find_elements(By.TAG_NAME, "table")
                            if posibles:
                                tabla = posibles[0]
                                break
                        except Exception:
                            pass
                        time.sleep(0.2)

                    # Si no se encontró la tabla aún, reintentar un clic en 'Ver información' y esperar de nuevo una vez
                    if tabla is None:
                        print("-> La tabla aún no aparece; reintentando clic en 'Ver información' y esperando de nuevo...")
                        try:
                            xpath_btn = "//input[starts-with(@id,'formBusqueda:j_idt') and @type='submit' and normalize-space(@value)='Ver información']"
                            elems = self.driver.find_elements(By.XPATH, xpath_btn)
                            if elems:
                                try:
                                    elems[0].click()
                                except Exception:
                                    try:
                                        self.driver.execute_script("arguments[0].click();", elems[0])
                                    except Exception:
                                        pass
                        except Exception:
                            pass
                        # Reintento de espera
                        end_time = time.time() + 10
                        while time.time() < end_time and tabla is None:
                            try:
                                contenedor_tabla = self.driver.find_element(By.ID, 'formBusqueda:tabla')
                                posibles = contenedor_tabla.find_elements(By.CSS_SELECTOR, "table.rf-dt")
                                if not posibles:
                                    posibles = contenedor_tabla.find_elements(By.TAG_NAME, "table")
                                if posibles:
                                    tabla = posibles[0]
                                    break
                            except Exception:
                                pass
                            time.sleep(0.2)

                    if tabla is None:
                        print("-> No se pudo localizar la tabla dentro de 'formBusqueda:tabla'")
                        return None

                    print("-> Extrayendo la tabla de resultados específica")

                    # Intentar ubicar el cuerpo de filas de datos (tbody que termina en :tb)
                    try:
                        tbody = tabla.find_element(By.CSS_SELECTOR, "tbody[id$=':tb']")
                    except Exception:
                        tbody = tabla.find_element(By.TAG_NAME, "tbody")

                    filas = tbody.find_elements(By.CSS_SELECTOR, "tr.rf-dt-r, tr")

                    fila_resultado = None
                    from selenium.common.exceptions import StaleElementReferenceException
                    for f in filas:
                        # Intentar extraer los textos de la fila con reintento por staleness
                        for intento_row in range(2):
                            try:
                                celdas = f.find_elements(By.TAG_NAME, "td")
                                if len(celdas) >= 7:
                                    # Tomar la primera fila válida
                                    num = (celdas[0].text or '').strip() or 0
                                    institucion = (celdas[1].text or '').strip() or 0
                                    titulo = (celdas[2].text or '').strip() or 0
                                    especialidad = (celdas[3].text or '').strip() or 0
                                    fecha_grado = (celdas[4].text or '').strip() or 0
                                    refrendacion = (celdas[5].text or '').strip() or 0
                                    # Última celda normalmente contiene el enlace "Imprimir"
                                    try:
                                        accion_text = (celdas[6].text or '').strip() or 'Imprimir'
                                    except StaleElementReferenceException:
                                        # Reintentar una vez releyendo las celdas
                                        celdas = f.find_elements(By.TAG_NAME, "td")
                                        accion_text = (celdas[6].text or '').strip() or 'Imprimir'

                                    fila_resultado = [num, str(cedula), nombre_persona, institucion, titulo, especialidad, fecha_grado, refrendacion, accion_text]
                                    break
                                break
                            except StaleElementReferenceException:
                                if intento_row == 0:
                                    time.sleep(0.2)
                                    continue
                                else:
                                    break
                        if fila_resultado:
                            break

                    if fila_resultado:
                        print(f"-> Fila extraída: {fila_resultado}")
                        return fila_resultado
                    else:
                        print("-> No se encontraron filas de datos en la tabla específica")
                        return None

                else:
                    print(f"-> Captcha no resuelto en el intento {intento + 1}")
                    if intento < max_reintentos - 1:
                        print(
                            "-> Recargando para obtener un captcha nuevo y "
                            "conservar la misma cédula."
                        )
                        self.recargar_para_nuevo_captcha(cedula)

            return None
        finally:
            print("-> Cerrando el navegador...")
            # self.driver.quit() Cerrar el driver del browser

    def procesar_masivo_desde_excel(self, archivo_entrada, archivo_salida):
        df = pd.read_excel(archivo_entrada, dtype={'Cedula': str})
        cedulas = df['Cedula']

        # Crear el DataFrame
        columnas = ['Nº', 'Cédula', 'Nombre', 'Institución', 'Título', 'Especialidad', 'Fecha Grado', 'Refrendación',
                    'Acción']
        df_resultados = pd.DataFrame(columns=columnas)

        # Recorrer las c.c y obtener los resultados
        for cedula in cedulas:
            print(f"Procesando cédula: {cedula}")
            resultado = self.obtener_informacion_educativa(cedula)

            # Si hay un resultado, lo agregamos; si no, agregamos la cédula con ceros
            if resultado:
                # Mantener compatibilidad con posibles respuestas de texto antiguas.
                primer_valor = resultado[0] if resultado else ""
                if (
                    isinstance(primer_valor, str)
                    and "No existe registro" in primer_valor
                ):
                    print(f"No hay registro de título para la cédula {cedula}")
                    fila = [0, cedula, 0, 0, 0, 0, 0, 0, 0]
                else:
                    fila = resultado
            else:
                print(
                    f"Sin información para la cédula {cedula}; "
                    "se guardará una fila con ceros."
                )
                fila = [0, cedula, 0, 0, 0, 0, 0, 0, 0]

            # Agregar la fila al DataFrame
            df_resultados = pd.concat([df_resultados, pd.DataFrame([fila], columns=columnas)], ignore_index=True)

            # Guardar el archivo Excel después de cada iteración
            df_resultados.to_excel(archivo_salida, index=False)

        print(f"Resultados guardados en {archivo_salida}")


# Main block ,,
if __name__ == "__main__":
    servicio_scraping = ScrapingService()
    archivo_entrada = os.path.join(base_dir, 'cedulas_entrada.xlsx')
    archivo_salida = os.path.join(base_dir, 'cedulas_salida.xlsx')
    servicio_scraping.procesar_masivo_desde_excel(archivo_entrada, archivo_salida)

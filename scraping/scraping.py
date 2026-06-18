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

    def obtener_informacion_educativa(self, cedula):
        """Realizar el scraping para obtener la información educativa de una cédula."""
        try:
            print(f"-> Accediendo a la página con la cédula: {cedula}")
            self.driver.get(config.URL)

            # Valor por defecto para el nombre (se llenará tras 'Consultar')
            nombre_persona = 0

            # Antes de ingresar la cédula, seleccionar el radio requerido para habilitar el campo (robusto)
            print("-> Seleccionando el tipo de búsqueda (radio) antes de ingresar la cédula")
            from selenium.common.exceptions import StaleElementReferenceException
            radio_seleccionado = False
            for intento_radio in range(5):
                try:
                    radio_opcion = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.ID, 'formBusqueda:selecItem:0'))
                    )
                    # Si no está seleccionado, intentar clic (normal y luego JS)
                    if not radio_opcion.is_selected():
                        try:
                            WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable((By.ID, 'formBusqueda:selecItem:0')))
                            radio_opcion.click()
                        except Exception:
                            try:
                                self.driver.execute_script("arguments[0].click();", radio_opcion)
                            except Exception:
                                pass
                    # Verificar estado seleccionado y que el input de cédula esté habilitado
                    WebDriverWait(self.driver, 10).until(
                        lambda d: d.find_element(By.ID, 'formBusqueda:cedula').is_enabled()
                    )
                    # Re-obtener el radio para evitar staleness y comprobar selección definitiva
                    radio_opcion = self.driver.find_element(By.ID, 'formBusqueda:selecItem:0')
                    if radio_opcion.is_selected():
                        radio_seleccionado = True
                        print("-> Radio de cédula seleccionado y campo habilitado")
                        time.sleep(1)  # Esperar 1 segundo después de marcar el radio antes de escribir la cédula
                        break
                except StaleElementReferenceException:
                    time.sleep(0.3)
                    continue
                except Exception as e:
                    print(f"   Aviso (intento {intento_radio+1}/5) al seleccionar radio: {e}")
                    time.sleep(0.3)
            if not radio_seleccionado:
                print("Advertencia: No se pudo asegurar la selección del radio de cédula. Reintentando igualmente el ingreso...")

            print("-> Ingresando la cédula en el formulario")
            # Reubicar y escribir en el campo de cédula con reintentos por staleness
            intentos_stale = 3
            ultima_excepcion = None
            for _ in range(intentos_stale):
                try:
                    # Esperar a que el input exista y sea interactuable (tras el AJAX del radio)
                    cedula_input = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.ID, 'formBusqueda:cedula'))
                    )
                    try:
                        cedula_input.clear()
                    except Exception:
                        pass
                    cedula_input.send_keys(str(cedula))
                    ultima_excepcion = None
                    break
                except Exception as e:
                    from selenium.common.exceptions import StaleElementReferenceException
                    ultima_excepcion = e
                    if isinstance(e, StaleElementReferenceException):
                        time.sleep(0.3)
                        continue
                    else:
                        # si es otro tipo de error, no insistir
                        break
            if ultima_excepcion:
                print(f"Advertencia: no se pudo escribir la cédula por: {ultima_excepcion}")

            max_reintentos = 5
            for intento in range(max_reintentos):
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

                    time.sleep(5)

                    try:
                        mensaje_error = self.driver.find_element(By.ID, 'formBusqueda:validarCaptcha').text
                        if "El captcha ingresado es incorrecto" in mensaje_error:
                            print("-> Captcha incorrecto. Re-marcando radio de cédula, reingresando cédula y renovando captcha...")
                            # 1) Volver a marcar el radio de cédula para asegurar que el input quede habilitado
                            try:
                                from selenium.common.exceptions import StaleElementReferenceException
                                for intento_radio in range(3):
                                    try:
                                        radio = WebDriverWait(self.driver, 10).until(
                                            EC.presence_of_element_located((By.ID, 'formBusqueda:selecItem:0'))
                                        )
                                        if not radio.is_selected():
                                            try:
                                                WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable((By.ID, 'formBusqueda:selecItem:0')))
                                                radio.click()
                                            except Exception:
                                                try:
                                                    self.driver.execute_script("arguments[0].click();", radio)
                                                except Exception:
                                                    pass
                                        # Esperar a que el input de cédula esté habilitado
                                        WebDriverWait(self.driver, 10).until(
                                            lambda d: d.find_element(By.ID, 'formBusqueda:cedula').is_enabled()
                                        )
                                        break
                                    except StaleElementReferenceException:
                                        time.sleep(0.2)
                                        continue
                                    except Exception:
                                        time.sleep(0.2)
                                        continue
                            except Exception as e_radio:
                                print(f"   Aviso al re-seleccionar radio: {e_radio}")

                            # 2) Volver a ingresar la cédula (manejo de staleness)
                            try:
                                ultima_ex = None
                                for _ in range(3):
                                    try:
                                        cedula_input2 = WebDriverWait(self.driver, 10).until(
                                            EC.element_to_be_clickable((By.ID, 'formBusqueda:cedula'))
                                        )
                                        try:
                                            cedula_input2.clear()
                                        except Exception:
                                            pass
                                        cedula_input2.send_keys(str(cedula))
                                        ultima_ex = None
                                        break
                                    except Exception as e2:
                                        from selenium.common.exceptions import StaleElementReferenceException
                                        ultima_ex = e2
                                        if isinstance(e2, StaleElementReferenceException):
                                            time.sleep(0.3)
                                            continue
                                        else:
                                            break
                                if ultima_ex:
                                    print(f"   Aviso: no se pudo reescribir la cédula: {ultima_ex}")
                            except Exception as e_ced:
                                print(f"   Aviso al reingresar cédula: {e_ced}")

                            # 3) Opcional: Cambiar la imagen del captcha para forzar uno nuevo
                            try:
                                btns = self.driver.find_elements(By.NAME, 'formBusqueda:j_idt51')
                                if not btns:
                                    btns = self.driver.find_elements(By.ID, 'formBusqueda:j_idt51')
                                if btns:
                                    try:
                                        btns[0].click()
                                    except Exception:
                                        try:
                                            self.driver.execute_script("arguments[0].click();", btns[0])
                                        except Exception:
                                            pass
                                    # Dar un pequeño tiempo para que la imagen se regenere
                                    time.sleep(0.6)
                            except Exception:
                                pass

                            # Ir al siguiente intento del bucle principal
                            continue
                    except:
                        pass

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

                    # Paso requerido: antes de hacer clic en "Ver información", asegurar que se ha dado clic en "Consultar"
                    # y que ambos botones estén presentes; solo entonces proceder con "Ver información".
                    xpath_btn = "//input[starts-with(@id,'formBusqueda:j_idt') and @type='submit' and normalize-space(@value)='Ver información']"

                    # Asegurar que el captcha esté realmente escrito en su input antes de continuar con la secuencia protegida
                    try:
                        cap_input_chk = WebDriverWait(self.driver, 5).until(
                            EC.presence_of_element_located((By.ID, 'formBusqueda:captcha'))
                        )
                        try:
                            current_val = cap_input_chk.get_attribute('value') or ''
                        except Exception:
                            current_val = ''
                        if not current_val.strip() and captcha_resuelto and captcha_resuelto != 'NO':
                            try:
                                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cap_input_chk)
                            except Exception:
                                pass
                            try:
                                cap_input_chk.click()
                            except Exception:
                                try:
                                    self.driver.execute_script("arguments[0].click();", cap_input_chk)
                                except Exception:
                                    pass
                            try:
                                cap_input_chk.clear()
                            except Exception:
                                pass
                            cap_input_chk.send_keys(captcha_resuelto)
                            time.sleep(2)
                    except Exception:
                        # Si no se puede verificar, continuar; la secuencia protegida aún realizará clic en Consultar
                        pass

                    print("-> Secuencia protegida: asegurar 'Consultar' y presencia de 'Ver información' antes de continuar")
                    clicked_ver_info = False
                    for intento_vi in range(3):
                        # 1) Clic en Consultar
                        try:
                            consultar_btn = WebDriverWait(self.driver, 10).until(
                                EC.element_to_be_clickable((By.ID, 'formBusqueda:clBuscar'))
                            )
                            # pequeña espera para estabilizar DOM (ya se esperó 2s tras escribir captcha en el primer clic)
                            time.sleep(1.5)
                            try:
                                consultar_btn.click()
                            except Exception:
                                self.driver.execute_script("arguments[0].click();", consultar_btn)
                        except Exception as e_cons:
                            print(f"Aviso: no se pudo hacer clic en 'Consultar' (intento {intento_vi+1}/3): {e_cons}")

                        # 2) Esperar hasta 6s a que ambos estén presentes: 'Consultar' y 'Ver información'
                        boton_ver_info = None
                        t0 = time.time()
                        while time.time() - t0 < 6:
                            try:
                                # Verificar que 'Consultar' siga presente en DOM
                                _ = self.driver.find_elements(By.ID, 'formBusqueda:clBuscar')
                                # Buscar 'Ver información' por XPath genérico
                                elems = self.driver.find_elements(By.XPATH, xpath_btn)
                                if elems:
                                    boton_ver_info = elems[0]
                                    break
                            except Exception:
                                pass
                            time.sleep(0.3)

                        # 3) Si apareció, intentar clic estable en 'Ver información'
                        if boton_ver_info:
                            try:
                                WebDriverWait(self.driver, 10).until(
                                    EC.element_to_be_clickable((By.XPATH, xpath_btn))
                                )
                                try:
                                    boton_ver_info.click()
                                except Exception:
                                    self.driver.execute_script("arguments[0].click();", boton_ver_info)
                                clicked_ver_info = True
                                print("-> Clic en 'Ver información' realizado (se detectó presencia de ambos botones)")
                                time.sleep(1)
                                break
                            except Exception as e_click_vi:
                                print(f"Aviso: fallo al clicar 'Ver información' (intento {intento_vi+1}/3): {e_click_vi}")
                        else:
                            print("-> 'Ver información' no apareció tras 'Consultar'; reintentando...")

                    # Si no se logró, mantener el flujo de recuperación previo (re-Consultar y reintento)
                    if not clicked_ver_info:
                        print("Advertencia: no se pudo hacer clic en ningún botón 'Ver información' conocido tras la secuencia protegida")
                        # Antes de reintentar 'Consultar', aseguremos que el captcha esté escrito en su input
                        try:
                            cap_retry = WebDriverWait(self.driver, 5).until(
                                EC.presence_of_element_located((By.ID, 'formBusqueda:captcha'))
                            )
                            try:
                                cap_val = cap_retry.get_attribute('value') or ''
                            except Exception:
                                cap_val = ''
                            if (not cap_val.strip()) and captcha_resuelto and captcha_resuelto != 'NO':
                                try:
                                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cap_retry)
                                except Exception:
                                    pass
                                try:
                                    cap_retry.click()
                                except Exception:
                                    try:
                                        self.driver.execute_script("arguments[0].click();", cap_retry)
                                    except Exception:
                                        pass
                                try:
                                    cap_retry.clear()
                                except Exception:
                                    pass
                                cap_retry.send_keys(captcha_resuelto)
                                time.sleep(2)
                        except Exception:
                            pass
                        try:
                            consultar_btn_retry = WebDriverWait(self.driver, 8).until(
                                EC.element_to_be_clickable((By.ID, 'formBusqueda:clBuscar'))
                            )
                            time.sleep(2)
                            try:
                                consultar_btn_retry.click()
                            except Exception:
                                self.driver.execute_script("arguments[0].click();", consultar_btn_retry)
                            try:
                                boton_retry = WebDriverWait(self.driver, 10).until(
                                    EC.element_to_be_clickable((By.XPATH, xpath_btn))
                                )
                                try:
                                    boton_retry.click()
                                except Exception:
                                    self.driver.execute_script("arguments[0].click();", boton_retry)
                                print("-> 'Ver información' clicado tras reintentar 'Consultar'")
                                clicked_ver_info = True
                                time.sleep(1)
                            except Exception as e_retry_vi:
                                print(f"Aviso: tras reintentar 'Consultar' no apareció 'Ver información': {e_retry_vi}")
                        except Exception as e_cons2:
                            print(f"Aviso: no se pudo reintentar 'Consultar': {e_cons2}")

                    # Si no se logró hacer clic en 'Ver información', no continuar a esperar la tabla; reintentar en el siguiente ciclo
                    if not clicked_ver_info:
                        print("-> No se logró hacer clic en 'Ver información' tras asegurar 'Consultar'. Reintentaremos en el siguiente intento del captcha.")
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
                # Si el resultado contiene "No existe registro", lo manejamos con ceros
                if "No existe registro" in resultado[0]:
                    print(f"No hay registro de título para la cédula {cedula}")
                    fila = [0, cedula, 0, 0, 0, 0, 0, 0, 0]  # Agregamos la cédula con los valores '0'
                else:
                    fila = resultado
            else:
                # En caso de None también poner 0's
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

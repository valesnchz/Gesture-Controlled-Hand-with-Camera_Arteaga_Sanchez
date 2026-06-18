idf_component_register(SRCS "main.c"
                        INCLUDE_DIRS "."
                        REQUIRES driver esp_wifi nvs_flash esp_http_server esp_timer esp_event esp32-camera)

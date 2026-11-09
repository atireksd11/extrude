#include "BluetoothA2DPSource.h"
#include "driver/i2s.h"

BluetoothA2DPSource a2dp_source;

const i2s_port_t i2s_num = I2S_NUM_0;

int32_t get_data_callback(uint8_t *data, size_t len) {
  size_t bytes_read = 0;
  i2s_read(i2s_num, data, len, &bytes_read, portMAX_DELAY);
  return bytes_read;
}

void setup() {
  i2s_config_t i2s_config = {
    .mode = (i2s_mode_t)(I2S_MODE_SLAVE | I2S_MODE_RX),
    .sample_rate = 44100,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
    .channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT,
    .communication_format = I2S_COMM_FORMAT_I2S,
    .intr_alloc_flags = 0,
    .dma_buf_count = 8,
    .dma_buf_len = 64,
    .use_apll = false,
    .tx_desc_auto_clear = false,
    .fixed_mclk = 0
  };

  i2s_pin_config_t pin_config = {
    .bck_io_num = 14,
    .ws_io_num = 28,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num = 34
  };

  i2s_driver_install(i2s_num, &i2s_config, 0, NULL);
  i2s_set_pin(i2s_num, &pin_config);

  a2dp_source.set_data_callback(get_data_callback);
  a2dp_source.start("AirPods");
}

void loop() {
}

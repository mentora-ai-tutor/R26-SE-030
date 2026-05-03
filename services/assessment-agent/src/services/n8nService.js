const axios = require('axios');

const startSession = async (payload) => {
  try {
    const url = `${process.env.N8N_BASE_URL}${process.env.N8N_WEBHOOK_PATH}/ame/start-session`;
    console.log('[n8n] POST', url);
    console.log('[n8n] Payload:', JSON.stringify(payload, null, 2));
    const response = await axios.post(url, payload, {
      timeout: 900000,
      headers: { 'Content-Type': 'application/json' },
    });
    console.log('[n8n] Response status:', response.status);
    console.log('[n8n] Response data type:', typeof response.data);
    console.log('[n8n] Response data:', response.data);
    return response.data;
  } catch (error) {
    console.error('[n8n] Error:', error.message);
    console.error('[n8n] Error code:', error.code);
    if (error.response) {
      console.error('[n8n] Response status:', error.response.status);
      console.error('[n8n] Response data:', error.response.data);
    }
    if (error.response && error.response.data) {
      throw new Error(error.response.data.message || 'n8n workflow error');
    }
    throw new Error(error.message || 'n8n workflow error');
  }
};

const submitAnswer = async (payload) => {
  try {
    const url = `${process.env.N8N_BASE_URL}${process.env.N8N_WEBHOOK_PATH}/ame/submit-answer`;
    console.log('[n8n] POST', url);
    console.log('[n8n] Payload:', JSON.stringify(payload, null, 2));
    const response = await axios.post(url, payload, {
      timeout: 900000,
      headers: { 'Content-Type': 'application/json' },
    });
    console.log('[n8n] Response status:', response.status);
    console.log('[n8n] Response data type:', typeof response.data);
    console.log('[n8n] Response data:', response.data);
    return response.data;
  } catch (error) {
    console.error('[n8n] Error:', error.message);
    if (error.response) {
      console.error('[n8n] Response status:', error.response.status);
      console.error('[n8n] Response data:', JSON.stringify(error.response.data, null, 2));
    }
    if (error.response && error.response.data) {
      throw new Error(error.response.data.message || 'n8n workflow error');
    }
    throw new Error(error.message || 'n8n workflow error');
  }
};

module.exports = { startSession, submitAnswer };

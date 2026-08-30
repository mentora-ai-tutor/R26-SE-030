const axios = require('axios');

const N8N_TIMEOUT = Number(process.env.N8N_TIMEOUT || 600000);

const startSession = async (payload) => {
  try {
    const url = `${process.env.N8N_BASE_URL}${process.env.N8N_WEBHOOK_PATH}/ame/start-session`;
    console.log('[n8n] POST', url);
    const response = await axios.post(url, payload, {
      timeout: N8N_TIMEOUT,
      headers: { 'Content-Type': 'application/json', 'Accept-Encoding': 'gzip, deflate' },
    });
    console.log('[n8n] Response status:', response.status);
    return response.data;
  } catch (error) {
    console.error('[n8n] Error:', error.message);
    if (error.code === 'ECONNABORTED') {
      throw new Error('n8n workflow timed out - the workflow may be stuck or taking too long to process');
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
    const response = await axios.post(url, payload, {
      timeout: N8N_TIMEOUT,
      headers: { 'Content-Type': 'application/json', 'Accept-Encoding': 'gzip, deflate' },
    });
    console.log('[n8n] Response status:', response.status);
    return response.data;
  } catch (error) {
    console.error('[n8n] Error:', error.message);
    if (error.code === 'ECONNABORTED') {
      throw new Error('n8n workflow timed out - the workflow may be stuck or taking too long to process');
    }
    if (error.response && error.response.data) {
      throw new Error(error.response.data.message || 'n8n workflow error');
    }
    throw new Error(error.message || 'n8n workflow error');
  }
};

const runCode = async (payload) => {
  try {
    const url = `${process.env.N8N_BASE_URL}${process.env.N8N_WEBHOOK_PATH}/ame/run-code`;
    console.log('[n8n] POST', url);
    const response = await axios.post(url, payload, {
      timeout: Number(process.env.SANDBOX_TIMEOUT || 60000),
      headers: { 'Content-Type': 'application/json', 'Accept-Encoding': 'gzip, deflate' },
    });
    console.log('[n8n] Response status:', response.status);
    return response.data;
  } catch (error) {
    console.error('[n8n] Error:', error.message);
    if (error.code === 'ECONNABORTED') {
      throw new Error('Code sandbox execution timed out');
    }
    if (error.response && error.response.data) {
      throw new Error(error.response.data.message || 'Code sandbox error');
    }
    throw new Error(error.message || 'Code sandbox error');
  }
};

module.exports = { startSession, submitAnswer, runCode };

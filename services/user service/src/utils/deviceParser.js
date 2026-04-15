const useragent = require('useragent');

/**
 * Parse user agent string to extract device information
 * @param {string} userAgentString - Raw user agent string
 * @returns {Object} Parsed device info
 */
const parseDeviceInfo = (userAgentString) => {
  if (!userAgentString) {
    return {
      type: 'unknown',
      os: 'unknown',
      browser: 'unknown',
      browser_version: 'unknown',
    };
  }

  const agent = useragent.parse(userAgentString);

  // Determine device type
  let type = 'desktop';
  const ua = userAgentString.toLowerCase();
  if (/mobile|android|iphone|ipad|ipod/.test(ua)) {
    if (/ipad|tablet/.test(ua) || (/>?</i.test(ua) && !/mobile/.test(ua))) {
      type = 'tablet';
    } else {
      type = 'mobile';
    }
  }

  return {
    type,
    os: agent.os.family || 'unknown',
    browser: agent.family || 'unknown',
    browser_version: agent.toVersion(),
  };
};

/**
 * Generate a device fingerprint
 * @param {string} userAgent - User agent string
 * @param {string} ip - IP address
 * @returns {string} Device fingerprint hash
 */
const generateDeviceId = (userAgent, ip) => {
  const crypto = require('crypto');
  const data = `${userAgent || ''}:${ip || ''}`;
  return crypto.createHash('sha256').update(data).digest('hex').substring(0, 16);
};

/**
 * Get device name from user agent
 * @param {Object} deviceInfo - Parsed device info
 * @returns {string} Human readable device name
 */
const getDeviceName = (deviceInfo) => {
  const parts = [];
  if (deviceInfo.browser !== 'unknown') {
    parts.push(deviceInfo.browser);
  }
  if (deviceInfo.os !== 'unknown') {
    parts.push(`on ${deviceInfo.os}`);
  }
  return parts.length > 0 ? parts.join(' ') : 'Unknown Device';
};

module.exports = {
  parseDeviceInfo,
  generateDeviceId,
  getDeviceName,
};

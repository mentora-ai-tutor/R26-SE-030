const express = require('express');
const router = express.Router();
const { auth } = require('../middleware/auth');
const ragController = require('../controllers/ragController');

router.post('/rag/ingest', auth, ragController.ingest);
router.post('/rag/retrieve', auth, ragController.retrieve);
router.get('/rag/documents', auth, ragController.listDocuments);
router.get('/rag/documents/:documentId', auth, ragController.getDocument);
router.delete('/rag/documents/:documentId', auth, ragController.deleteDocument);
router.get('/rag/stats', auth, ragController.getStats);

module.exports = router;

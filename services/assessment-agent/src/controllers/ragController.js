const mongoose = require('mongoose');
const ragService = require('../services/ragService');

const ingest = async (req, res, next) => {
  try {
    const db = mongoose.connection.db;
    const result = await ragService.ingestDocument(db, req.body);

    res.status(200).json({
      success: true,
      message: 'Document ingested into the knowledge base',
      data: result,
    });
  } catch (error) {
    next({
      statusCode: 500,
      message: 'Failed to ingest document',
      error: error.message,
    });
  }
};

const retrieve = async (req, res, next) => {
  try {
    const db = mongoose.connection.db;
    const { query, topic, document_id, top_k, threshold } = req.body;

    if (!query || !String(query).trim()) {
      return res.status(400).json({
        success: false,
        message: 'query is required',
      });
    }

    const result = await ragService.retrieve(db, query, {
      topic,
      document_id,
      top_k,
      threshold,
    });

    res.status(200).json({
      success: true,
      data: result,
    });
  } catch (error) {
    next({
      statusCode: 500,
      message: 'Failed to retrieve context',
      error: error.message,
    });
  }
};

const listDocuments = async (req, res, next) => {
  try {
    const db = mongoose.connection.db;
    const page = parseInt(req.query.page, 10) || 1;
    const limit = parseInt(req.query.limit, 10) || 20;

    const result = await ragService.listDocuments(db, page, limit);

    res.status(200).json({
      success: true,
      data: result,
    });
  } catch (error) {
    next({
      statusCode: 500,
      message: 'Failed to list knowledge base documents',
      error: error.message,
    });
  }
};

const getDocument = async (req, res, next) => {
  try {
    const db = mongoose.connection.db;
    const { documentId } = req.params;

    const result = await ragService.getDocument(db, documentId);

    if (!result) {
      return res.status(404).json({
        success: false,
        message: 'Knowledge base document not found',
      });
    }

    res.status(200).json({
      success: true,
      data: result,
    });
  } catch (error) {
    next({
      statusCode: 500,
      message: 'Failed to retrieve knowledge base document',
      error: error.message,
    });
  }
};

const deleteDocument = async (req, res, next) => {
  try {
    const db = mongoose.connection.db;
    const { documentId } = req.params;

    const result = await ragService.deleteDocument(db, documentId);

    if (!result.deleted) {
      return res.status(404).json({
        success: false,
        message: 'Knowledge base document not found',
      });
    }

    res.status(200).json({
      success: true,
      message: 'Knowledge base document deleted',
      data: result,
    });
  } catch (error) {
    next({
      statusCode: 500,
      message: 'Failed to delete knowledge base document',
      error: error.message,
    });
  }
};

const getStats = async (req, res, next) => {
  try {
    const db = mongoose.connection.db;
    const result = await ragService.getStats(db);

    res.status(200).json({
      success: true,
      data: result,
    });
  } catch (error) {
    next({
      statusCode: 500,
      message: 'Failed to retrieve knowledge base stats',
      error: error.message,
    });
  }
};

module.exports = {
  ingest,
  retrieve,
  listDocuments,
  getDocument,
  deleteDocument,
  getStats,
};

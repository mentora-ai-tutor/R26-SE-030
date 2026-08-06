const fs = require('fs');
const path = require('path');
const { connectDB, disconnectDB } = require('../src/config/db');
const logger = require('../src/utils/logger');
const { validateGraphAcyclic, seedGraph } = require('../src/services/conceptGraph.service');

const SEED_PATH = path.resolve(__dirname, '..', 'seed', 'java_oop_graph.json');

const main = async () => {
  await connectDB();

  try {
    const raw = fs.readFileSync(SEED_PATH, 'utf8');
    const nodes = JSON.parse(raw);

    logger.info('Loading concept graph seed', { node_count: nodes.length });

    const summary = await seedGraph(nodes);

    logger.info('Concept graph seeded successfully', summary);
  } catch (error) {
    logger.error('Concept graph seeding failed', { error: error.message });
    process.exitCode = 1;
  } finally {
    await disconnectDB();
  }
};

if (require.main === module) {
  main();
}

module.exports = { validateGraphAcyclic };

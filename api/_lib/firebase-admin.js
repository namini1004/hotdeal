const admin = require('firebase-admin');

function readServiceAccount() {
  const raw = process.env.FIREBASE_SERVICE_ACCOUNT_JSON || '';
  if (!raw) return null;

  try {
    if (raw.trim().startsWith('{')) return JSON.parse(raw);
    return require(raw);
  } catch (error) {
    throw new Error(`Invalid FIREBASE_SERVICE_ACCOUNT_JSON: ${error.message}`);
  }
}

function getFirebaseApp() {
  if (admin.apps.length) return admin.app();

  const serviceAccount = readServiceAccount();
  if (!serviceAccount) {
    throw new Error('Missing FIREBASE_SERVICE_ACCOUNT_JSON');
  }

  return admin.initializeApp({
    credential: admin.credential.cert(serviceAccount),
    projectId: process.env.FIREBASE_PROJECT_ID || serviceAccount.project_id,
  });
}

function firestore() {
  return getFirebaseApp().firestore();
}

function messaging() {
  return getFirebaseApp().messaging();
}

module.exports = {
  firestore,
  messaging,
};

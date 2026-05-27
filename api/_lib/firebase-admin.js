const admin = require('firebase-admin');
const { getFirestore } = require('firebase-admin/firestore');

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
  const app = getFirebaseApp();
  const databaseId = String(process.env.FIREBASE_DATABASE_ID || '').trim();
  if (databaseId) return getFirestore(app, databaseId);
  return getFirestore(app);
}

function messaging() {
  return getFirebaseApp().messaging();
}

function firebaseDebugInfo() {
  const raw = process.env.FIREBASE_SERVICE_ACCOUNT_JSON || '';
  let serviceAccountProjectId = '';
  try {
    if (raw.trim().startsWith('{')) {
      serviceAccountProjectId = String(JSON.parse(raw).project_id || '');
    } else if (raw) {
      // path mode (vercel env can point to mounted file in local dev)
      // eslint-disable-next-line global-require, import/no-dynamic-require
      serviceAccountProjectId = String(require(raw).project_id || '');
    }
  } catch (_) {
    serviceAccountProjectId = '';
  }

  return {
    firebaseProjectIdEnv: String(process.env.FIREBASE_PROJECT_ID || ''),
    serviceAccountProjectId,
    firestoreDatabaseId: String(process.env.FIREBASE_DATABASE_ID || '(default)'),
  };
}

module.exports = {
  firestore,
  messaging,
  firebaseDebugInfo,
};

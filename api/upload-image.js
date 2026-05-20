const crypto = require('crypto');

function json(res, code, data) {
  res.statusCode = code;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.end(JSON.stringify(data));
}

function supabaseConfig() {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) throw new Error('Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY');
  return { url, key };
}

async function ensureBucket(url, key, bucket) {
  const listRes = await fetch(`${url}/storage/v1/bucket`, {
    headers: { apikey: key, Authorization: `Bearer ${key}` },
  });
  if (!listRes.ok) throw new Error(`bucket list failed(${listRes.status})`);
  const buckets = await listRes.json();
  if ((buckets || []).some((b) => b.name === bucket)) return;

  const createRes = await fetch(`${url}/storage/v1/bucket`, {
    method: 'POST',
    headers: {
      apikey: key,
      Authorization: `Bearer ${key}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ name: bucket, public: true, file_size_limit: 2097152 }),
  });
  if (!createRes.ok) {
    const text = await createRes.text();
    if (!text.includes('already exists')) {
      throw new Error(`bucket create failed(${createRes.status}): ${text}`);
    }
  }
}

function parseDataUri(dataUri = '') {
  const match = String(dataUri).match(/^data:(image\/[a-zA-Z0-9.+-]+);base64,(.+)$/);
  if (!match) throw new Error('invalid data URI');
  const mime = match[1].toLowerCase();
  const b64 = match[2];
  const ext = mime.includes('png') ? 'png' : 'jpg';
  const bytes = Buffer.from(b64, 'base64');
  return { mime, ext, bytes };
}

module.exports = async (req, res) => {
  try {
    if (req.method !== 'POST') {
      res.setHeader('Allow', 'POST');
      return json(res, 405, { error: 'Method not allowed' });
    }

    const { imageData, folder = 'user', filename = '' } = req.body || {};
    if (!imageData) return json(res, 400, { error: 'imageData is required' });

    const { url, key } = supabaseConfig();
    const bucket = 'hotdeal-images';
    await ensureBucket(url, key, bucket);

    const { mime, ext, bytes } = parseDataUri(imageData);
    if (bytes.length > 2 * 1024 * 1024) {
      return json(res, 400, { error: 'image too large (max 2MB)' });
    }

    const safeFolder = String(folder).replace(/[^a-zA-Z0-9/_-]/g, '') || 'user';
    const base = String(filename || '').replace(/[^a-zA-Z0-9._-]/g, '').replace(/\.[a-zA-Z0-9]+$/, '');
    const hash = crypto.randomBytes(6).toString('hex');
    const name = `${Date.now()}-${hash}${base ? `-${base}` : ''}.${ext}`;
    const objectPath = `${safeFolder}/${name}`;

    const uploadRes = await fetch(`${url}/storage/v1/object/${bucket}/${objectPath}`, {
      method: 'POST',
      headers: {
        apikey: key,
        Authorization: `Bearer ${key}`,
        'Content-Type': mime,
        'x-upsert': 'false',
      },
      body: bytes,
    });

    if (!uploadRes.ok) {
      const text = await uploadRes.text();
      throw new Error(`upload failed(${uploadRes.status}): ${text}`);
    }

    const publicUrl = `${url}/storage/v1/object/public/${bucket}/${objectPath}`;
    return json(res, 201, { url: publicUrl, path: objectPath, size: bytes.length, bucket });
  } catch (error) {
    return json(res, 500, { error: error.message || 'upload failed' });
  }
};

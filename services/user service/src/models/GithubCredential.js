const mongoose = require('mongoose');

const githubCredentialSchema = new mongoose.Schema(
  {
    student_id: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'Student',
      required: true,
      unique: true,
      index: true,
    },
    gh_user_id: { type: Number, required: true },
    gh_login: { type: String, required: true },
    scopes: { type: [String], default: [] },
    ciphertext: { type: Buffer, required: true },
    iv: { type: Buffer, required: true },
    tag: { type: Buffer, required: true },
    linked_at: { type: Date, default: Date.now },
    last_used_at: { type: Date },
  },
  { timestamps: true },
);

module.exports = mongoose.model('GithubCredential', githubCredentialSchema);

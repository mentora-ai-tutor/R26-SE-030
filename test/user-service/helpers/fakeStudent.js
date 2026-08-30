class FakeStudent {
  constructor(data = {}) {
    const defaults = {
      _id: 'stu_0001',
      student_id: 'STD-00001',
      name: 'Jane Doe',
      email: 'jane@example.com',
      role: 'student',
      profile: { avatar_url: '', bio: '', java_level: 'beginner', institution: '', country: '' },
      stats: {
        overall_mastery_score: 0,
        total_materials_generated: 0,
        total_sessions: 0,
        last_mastery_update: null,
      },
      preferences: {
        notifications: { email: true, push: true, marketing: false },
        theme: 'system',
        language: 'en',
        timezone: 'UTC',
      },
      is_active: true,
      is_verified: false,
      is_deleted: false,
    };
    Object.assign(this, defaults, data);
  }

  toObject() {
    const out = {};
    for (const key of Object.keys(this)) out[key] = this[key];
    return out;
  }

  toSafeObject() {
    const obj = this.toObject();
    delete obj.password;
    delete obj.refresh_token;
    delete obj.__v;
    return obj;
  }

  async save() {
    return this;
  }

  async comparePassword(candidate) {
    return candidate === this._plainPassword || candidate === this.password;
  }

  async softDelete(deletedBy) {
    this.is_deleted = true;
    this.is_active = false;
    this.deleted_at = new Date();
    if (deletedBy) this.deleted_by = deletedBy;
    return this;
  }
}

FakeStudent.findById = undefined;
FakeStudent.findByIdAndUpdate = undefined;
FakeStudent.findOne = undefined;
FakeStudent.findOneAndUpdate = undefined;
FakeStudent.countDocuments = undefined;
FakeStudent.create = undefined;
FakeStudent.aggregate = undefined;
FakeStudent.find = undefined;
FakeStudent.hashRefreshToken = undefined;

module.exports = FakeStudent;
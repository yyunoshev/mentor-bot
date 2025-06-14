// Создание пользователя базы данных
db = db.getSiblingDB('ai_chat_bot');

db.createUser({
  user: 'botuser',
  pwd: 'botpassword',
  roles: [
    {
      role: 'readWrite',
      db: 'ai_chat_bot'
    }
  ]
});

// Создание коллекций с индексами
db.createCollection('users');
db.createCollection('chats');

// Создание индексов для оптимизации
db.users.createIndex({ "user_id": 1 }, { unique: true });
db.chats.createIndex({ "user_id": 1, "timestamp": -1 });

print('База данных ai_chat_bot инициализирована успешно!');
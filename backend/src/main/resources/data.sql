INSERT INTO sys_user (id, username, password_hash, nickname, avatar_url, role, status)
VALUES
  (1, 'admin', '{noop}123456', '管理员', 'avatar-compass', 'ADMIN', 1),
  (2, 'user', '{noop}123456', '旅行者', 'avatar-backpack', 'USER', 1)
ON DUPLICATE KEY UPDATE role = VALUES(role), status = VALUES(status);

INSERT INTO city (id, name, province, summary, best_season, image_url, sort_order)
VALUES
  (1, '成都', '四川', '适合轻松美食游，熊猫、古街、火锅和川西文化都很集中。', '3-6月、9-11月', 'oneclick-trip-assets/chengdu-destination.png', 1),
  (2, '杭州', '浙江', '西湖、灵隐寺和龙井村适合慢节奏城市自然游。', '3-5月、9-10月', NULL, 2),
  (3, '西安', '陕西', '古都文化和碳水美食密度高，适合历史路线。', '3-5月、9-11月', NULL, 3),
  (4, '大理', '云南', '苍山洱海和古城生活感强，适合放松度假。', '全年适合，3-5月更舒适', NULL, 4)
ON DUPLICATE KEY UPDATE summary = VALUES(summary), best_season = VALUES(best_season), image_url = VALUES(image_url);

INSERT INTO scenic_spot (id, city_id, name, address, summary, ticket_price, open_time, play_hours, rating, tags, sort_order)
VALUES
  (1, 1, '成都大熊猫繁育研究基地', '成都市成华区熊猫大道1375号', '适合上午前往，能看到更活跃的大熊猫。', 55, '07:30-18:00', 3.5, 4.8, '亲子,必去,轻松', 1),
  (2, 1, '宽窄巷子', '成都市青羊区长顺街附近', '成都老街区代表，适合散步和小吃。', 0, '全天开放', 2.0, 4.5, '街区,美食,拍照', 2),
  (3, 1, '杜甫草堂', '成都市青羊区青华路37号', '人文历史景点，适合半日安静游览。', 60, '09:00-18:00', 2.5, 4.6, '人文,历史', 3),
  (4, 1, '武侯祠', '成都市武侯区武侯祠大街231号', '三国文化主题景点，可和锦里一起安排。', 50, '09:00-18:00', 2.0, 4.6, '三国,历史', 4),
  (5, 2, '西湖', '杭州市西湖区', '杭州经典景观，适合骑行或步行慢游。', 0, '全天开放', 4.0, 4.9, '湖景,散步,拍照', 1),
  (6, 2, '灵隐寺', '杭州市西湖区法云弄1号', '人气寺院，建议上午前往。', 75, '07:00-18:00', 3.0, 4.7, '寺院,人文', 2),
  (7, 3, '秦始皇兵马俑', '西安市临潼区秦陵北路', '西安核心历史景点，建议预留半天。', 120, '08:30-18:00', 4.0, 4.8, '历史,必去', 1),
  (8, 3, '西安城墙', '西安市碑林区南大街', '可骑行看古城轮廓，傍晚体验更好。', 54, '08:00-22:00', 2.5, 4.7, '骑行,夜景', 2),
  (9, 4, '洱海生态廊道', '大理市洱海沿线', '适合骑行、拍照和轻松散步。', 0, '全天开放', 4.0, 4.8, '湖景,骑行', 1),
  (10, 4, '大理古城', '大理市一塔路42号', '适合夜间散步和吃饭，节奏轻松。', 0, '全天开放', 2.5, 4.5, '古城,美食', 2)
ON DUPLICATE KEY UPDATE summary = VALUES(summary), ticket_price = VALUES(ticket_price), rating = VALUES(rating);

INSERT INTO food (id, city_id, name, category, summary, recommended_area, avg_price, image_url, sort_order)
VALUES
  (1, 1, '火锅与串串', '晚餐首选', '适合安排在市区夜晚，人均 80-120 元，建议搭配轻松行程。', '春熙路、建设路', 100, 'oneclick-trip-assets/chengdu-food-hotpot.png', 1),
  (2, 1, '担担面与冰粉', '小吃集合', '适合午餐或景点间隙，价格轻，选择多，不会拖慢路线。', '宽窄巷子、锦里', 30, 'oneclick-trip-assets/chengdu-food-snacks.png', 2),
  (3, 2, '龙井茶点', '清淡茶食', '适合西湖或龙井村附近安排，节奏舒服。', '龙井村、满觉陇', 80, NULL, 1),
  (4, 2, '片儿川', '本地面食', '适合早餐或午餐，价格轻，体验杭州家常味。', '湖滨、武林', 25, NULL, 2),
  (5, 3, '肉夹馍与凉皮', '碳水小吃', '适合景点间隙快速补能，价格友好。', '回民街、钟楼', 30, NULL, 1),
  (6, 3, '羊肉泡馍', '正餐', '适合晚餐慢慢吃，注意分量较足。', '钟楼、小寨', 55, NULL, 2),
  (7, 4, '菌子火锅', '云南特色', '适合晚餐，雨季要选择正规餐厅。', '大理古城', 110, NULL, 1),
  (8, 4, '乳扇与鲜花饼', '轻食小吃', '适合古城散步时穿插体验。', '大理古城、喜洲', 35, NULL, 2)
ON DUPLICATE KEY UPDATE summary = VALUES(summary), avg_price = VALUES(avg_price), image_url = VALUES(image_url);

UPDATE food SET image_url = 'oneclick-trip-assets/hangzhou-longjing-snacks.png' WHERE id = 3;
UPDATE food SET image_url = 'oneclick-trip-assets/hangzhou-pianerchuan.png' WHERE id = 4;
UPDATE food SET image_url = 'oneclick-trip-assets/xian-roujiamo-liangpi.png' WHERE id = 5;
UPDATE food SET image_url = 'oneclick-trip-assets/xian-yangrou-paomo.png' WHERE id = 6;
UPDATE food SET image_url = 'oneclick-trip-assets/dali-mushroom-hotpot.png' WHERE id = 7;
UPDATE food SET image_url = 'oneclick-trip-assets/dali-rushan-flower-cake.png' WHERE id = 8;

INSERT INTO hotel (id, city_id, name, area, summary, price_level, avg_price, rating)
VALUES
  (1, 1, '春熙路舒适酒店', '春熙路/太古里', '交通方便，适合第一次来成都和美食路线。', 'MEDIUM', 360, 4.6),
  (2, 1, '宽窄巷子精品民宿', '宽窄巷子', '靠近老街区，晚上散步方便。', 'MEDIUM', 420, 4.5),
  (3, 2, '湖滨轻奢酒店', '西湖湖滨', '适合西湖路线，步行和打车都方便。', 'HIGH', 620, 4.7),
  (4, 3, '钟楼精选酒店', '钟楼/回民街', '适合古城墙和美食路线。', 'MEDIUM', 330, 4.5),
  (5, 4, '洱海边度假民宿', '洱海生态廊道', '适合慢节奏度假和看日出。', 'MEDIUM', 460, 4.6)
ON DUPLICATE KEY UPDATE summary = VALUES(summary), avg_price = VALUES(avg_price), rating = VALUES(rating);

INSERT INTO trip_template (id, city_id, title, days, budget_level, pace, summary, cover_url)
VALUES
  (1, 1, '成都3日经典游', 3, 'MEDIUM', 'RELAXED', '熊猫基地、古街、火锅和人文景点结合，适合第一次来成都。', 'oneclick-trip-assets/chengdu-destination.png'),
  (2, 2, '杭州2日西湖慢游', 2, 'MEDIUM', 'RELAXED', '西湖、灵隐寺、龙井茶村，适合轻松城市自然游。', NULL),
  (3, 3, '西安3日古都文化游', 3, 'MEDIUM', 'COMPACT', '兵马俑、城墙、大唐不夜城和碳水美食。', NULL),
  (4, 4, '大理4日慢生活', 4, 'MEDIUM', 'RELAXED', '洱海骑行、古城散步、喜洲和苍山轻度游。', NULL)
ON DUPLICATE KEY UPDATE summary = VALUES(summary), cover_url = VALUES(cover_url);

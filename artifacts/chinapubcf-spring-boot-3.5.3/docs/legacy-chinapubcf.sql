/*
Navicat MySQL Data Transfer

Source Server         : myconn
Source Server Version : 50146
Source Host           : localhost:3306
Source Database       : chinapubcf

Target Server Type    : MYSQL
Target Server Version : 50146
File Encoding         : 65001

Date: 2014-10-10 17:12:39
*/

SET FOREIGN_KEY_CHECKS=0;
-- ----------------------------
-- Table structure for `book`
-- ----------------------------
DROP TABLE IF EXISTS `book`;
CREATE TABLE `book` (
  `bookId` int(11) NOT NULL AUTO_INCREMENT,
  `originalName` varchar(64) DEFAULT NULL,
  `author` varchar(64) DEFAULT NULL,
  `name` varchar(64) DEFAULT NULL,
  `translator` varchar(32) DEFAULT NULL,
  `press` varchar(32) DEFAULT NULL,
  `seriesName` varchar(32) DEFAULT NULL,
  `isbn` varchar(32) DEFAULT NULL,
  `pressTime` varchar(32) DEFAULT NULL,
  `version` varchar(32) DEFAULT NULL,
  `shelfTime` varchar(32) DEFAULT NULL,
  `category` varchar(128) DEFAULT NULL,
  `price` float DEFAULT NULL,
  `vipPrice` float DEFAULT NULL,
  `schoolPrice` float DEFAULT NULL,
  `activity` varchar(32) DEFAULT NULL,
  `sales` varchar(32) DEFAULT NULL,
  PRIMARY KEY (`bookId`)
) ENGINE=InnoDB AUTO_INCREMENT=24 DEFAULT CHARSET=utf8;

-- ----------------------------
-- Records of book
-- ----------------------------
INSERT INTO `book` VALUES ('1', 'Java EE核心框架实战', ' 高洪岩', 'Java EE核心框架实战', '华章公司', '人民邮电出版社', null, '9787115365712', '2014 年9月', '1-1', '2014-9-12', '计算机 | 软件与程序设计 | JAVA(J#) | Java', '89', '66.75', '66.75', '[全场]客户端首单立减5元!满48元免邮(仅限普通快递及平邮)', '1232');
INSERT INTO `book` VALUES ('2', 'Java加密与解密的艺术(第2版)', ' 梁栋 ', 'Java加密与解密的艺术(第2版)', '华章公司', '机械工业出版社', '华章原创精品', '9787111446781', '2014 年1月', '2-1', '2013-11-27', '计算机 | 软件与程序设计 | JAVA(J#) | Java', '89', '60.52', '60.52', '[全场]客户端首单立减5元!满48元免邮(仅限普通快递及平邮)', '2112');
INSERT INTO `book` VALUES ('3', 'Java 7并发编程实战手册', '(西)Javier Fernandez Gonzalez  ', 'Java 7并发编程实战手册', ' 申绍勇 俞黎敏', '人民邮电出版社', null, '9787115335296', '2014 年2月', '1-1', '2014-1-22', '计算机 | 软件与程序设计 | JAVA(J#) | Java', '59', '44.25', '44.25', '[全场]客户端首单立减5元!满48元免邮(仅限普通快递及平邮)', '113');
INSERT INTO `book` VALUES ('4', 'Java程序员面试宝典(第三版)', '欧立奇    朱梅    段韬 ', 'Java程序员面试宝典(第三版)', '华章公司', '电子工业出版社', null, '9787121213137', '2013 年9月', '1-1', '2013-9-28', '计算机 | 软件与程序设计 | JAVA(J#) | Java', '49', '33.81', '33.81', '[全场]客户端首单立减5元!满48元免邮(仅限普通快递及平邮)', '33');
INSERT INTO `book` VALUES ('5', 'Core Java, Vol. 2: Advanced Features, 8th Edition', '(美)Cay S. Horstmann   Gary Cornell', 'Java核心技术 卷Ⅱ:高级特性(原书第8版)(china-pub 首发)', '陈昊鹏 王浩 姚建平', '机械工业出版社', 'Sun公司核心技术丛书', '9787111256113', '2008 年12月', '8-1', '2008-12-12', '计算机 | 软件与程序设计 | JAVA(J#) | Java', '118', '84.96', '84.96', '[全场]客户端首单立减5元!满48元免邮(仅限普通快递及平邮)', '423');
INSERT INTO `book` VALUES ('6', 'Introduction to Java Programming, Comprehensive (8th Edition)', '(美)Y.Daniel Liang   ', 'Java语言程序设计：进阶篇（英文版.第8版）', '华章公司', '机械工业出版社', '经典原版书库', '9787111361251', '2011 年10月', '8-1', '2011-11-24', '计算机 | 软件与程序设计 | JAVA(J#) | Java', '89', '60.52', '60.52', '[全场]客户端首单立减5元!满48元免邮(仅限普通快递及平邮)', '634');
INSERT INTO `book` VALUES ('7', null, '孙卫琴 ', 'Java面向对象编程(蓝皮)', '华章公司', '电子工业出版社', 'JAVA开发专家', '712102538811', '2006 年10月', '2-1', '2006-11-27', '计算机 | 软件与程序设计 | JAVA(J#) | Java', '65.8', '51.32', '52.64', '[全场]客户端首单立减5元!满48元免邮(仅限普通快递及平邮)', '167');
INSERT INTO `book` VALUES ('8', 'Thinking in Java (4th Edition)', ' (美)Bruce Eckel  ', 'Java编程思想(第4版)(第9届Jolt生产效率大奖、第13届Jolt震撼大奖获奖图书)(经典图书最新版本)', '陈昊鹏', '机械工业出版社', '计算机科学丛书', '9787111213826', '2007 年6月', '4-2', '2007-6-19', '教材 | 计算机教材 | 本科or研究生 | 计算机专业教材 计算机 | 软件与程序设计 | JAVA(J#) | 综合', '108', '75.6', '75.6', '[全场]客户端首单立减5元!满48元免邮(仅限普通快递及平邮)', '500');
INSERT INTO `book` VALUES ('9', 'iPhone Game Development: Developing 2D 3D games in Objective-C', '(美)Paul Zirkle   ', '(特价书)iPhone游戏开发', '张龙', '人民邮电出版社', '人民邮电出版社OReilly系列', '9787115252616', '2011 年7月', '3-1', '2014-4-24', '计算机｜游戏｜手机游戏设计', '45', '21.6', '21.6', '[全场]客户端首单立减5元!满48元免邮(仅限普通快递及平邮)', '200');
INSERT INTO `book` VALUES ('10', 'Applied Cryptography　Protocols,Algorithms,and Source Code in C', '(美)Bruce Schneier   ', '(特价书)应用密码学：协议算法与C源程序(原书第2版', ' 吴世忠 祝世雄 张文政', '机械工业出版社', '计算机科学丛书', '9787111445333', '2014 年1月', '2-1', '2014-5-26', '计算机｜教材｜信息安全', '79', '35.55', '35.55', '[全场]客户端首单立减5元!满48元免邮(仅限普通快递及平邮)', '120');
INSERT INTO `book` VALUES ('11', 'Object-Oriented Programming in C++（Second Edition)', '（美）Richard JohnsonbaughMartin Kalin   ', '(特价书)面向对象程序设计C++语言描述（原书第2版）', '蔡宇辉 李军义', '机械工业出版社', ' 程序设计语言译丛', '7111109473', '2003 年1月', '1-1', '2002-11-22', '计算机 软件与程序设计 C++ C++', '48', '19.2', '19.2', '[全场]客户端首单立减5元!满48元免邮(仅限普通快递及平邮)', '383');
INSERT INTO `book` VALUES ('12', 'API Design for C++', ' (美)Martin Reddy  ', 'C++ API设计', '刘晓娜 臧秀涛 林健', '人民邮电出版社', '图灵程序设计丛书', '9787115322999', '2013 年9月', '1-1', '2013-7-23', '计算机 软件与程序设计 C++ C++', '89', '66.75', '66.75', '[全场]客户端首单立减5元!满48元免邮(仅限普通快递及平邮)', '323');
INSERT INTO `book` VALUES ('13', 'Essential C++', ' (美)Stanley BLippman', 'Essential C++中文版', ' 侯捷', '电子工业出版社', '传世经典书丛', '9787121209345', '2013 年8月', '1-1', '2013-7-18', '计算机 软件与程序设计 C++ C++', '65', '48.75', '48.75', '[全场]客户端首单立减5元!满48元免邮(仅限普通快递及平邮)', '436');
INSERT INTO `book` VALUES ('14', 'Thinking in C++ Introduction to Practical Programming', ' (美)Bruce Eckel    Chuck Allison   ', 'C++编程思想(两卷合订本)(第6届Jolt生产效率大奖获奖图书)(第1卷标准C++导引第2卷实用编程技术)', ' 刘宗田 袁兆山 潘秋菱 刁成嘉', '机械工业出版社', ' 计算机科学丛书', '9787111350217', '2011 年7月', '1-1', '2011-7-18', '计算机 软件与程序设计 C++ C++', '69', '50.37', '50.37', '[全场]客户端首单立减5元!满48元免邮(仅限普通快递及平邮)', '654');
INSERT INTO `book` VALUES ('15', null, ' 明日科技 ', 'C++从入门到精通(第2版)', null, '清华大学出版社', '软件开发视频大讲堂', '9787112326501', '2012 年9月', '1-1', '2012-8-30', '计算机 软件与程序设计 C++ C++', '59.8', '40.75', '40.75', '[全场]客户端首单立减5元!满48元免邮(仅限普通快递及平邮)', '656');
INSERT INTO `book` VALUES ('16', null, 'Michael Wong    IBM XL编译器中国开发团队   ', '深入理解C++11：C++11新特性解析与应用', null, '机械工业出版社', ' 原创精品系列', '9787111426608', '2013 年6月', '1-1', '2013-5-31', '计算机 软件与程序设计 C++ C++', '69', '51.75', '51.75', '[全场]客户端首单立减5元!满48元免邮(仅限普通快递及平邮)', '325');
INSERT INTO `book` VALUES ('17', 'C++ Primer (5th Edition)', ' (美)Stanley B Lippman(斯坦利 李普曼) Josee Lajoie(约瑟 拉乔伊)  ', 'C++ Primer中文版(第5版)', '王刚 杨巨峰', '电子工业出版社', 'AddisonWesley Professional', '9787121155352', '2013 年9月', '1-1', '2013-8-21', '计算机 软件与程序设计 C++ C++', '128', '96', '96', '[全场]客户端首单立减5元!满48元免邮(仅限普通快递及平邮)', '765');
INSERT INTO `book` VALUES ('18', null, ' 冀云', 'C++黑客编程揭秘与防范', null, '人民邮电出版社', null, '9787115280640', '2012 年6月', '1-1', '2012-5-31', '合作专区微软技术图书微软程序设计 微软CC++VC++', '39', '29.25', '29.25', '[全场]客户端首单立减5元!满48元免邮(仅限普通快递及平邮)', '233');
INSERT INTO `book` VALUES ('19', null, ' [美]F Alexander Allain ', 'C++程序设计：现代方法(china-pub首发)', ' 赵守彬 陈园军 马兴旺', '人民邮电出版社', '图灵设计丛书', '9787115357007', '2014 年8月', '1-1', '2014-7-25', '计算机 软件与程序设计 C++ C++', '69', '53.13', '53.13', '[全场]客户端首单立减5元!满48元免邮(仅限普通快递及平邮)', '532');
INSERT INTO `book` VALUES ('20', null, ' 王慧    王浩   ', '零基础学C++(第3版)', null, '机械工业出版社', ' 零基础学编程', '9787111468592', '2014 年7月', '1-1', '2014-6-26', '计算机 软件与程序设计 C++ C++', '79', '51.35', '51.35', '[全场]客户端首单立减5元!满48元免邮(仅限普通快递及平邮)', '632');
INSERT INTO `book` VALUES ('21', null, 'Stephen Prata', 'C++ Primer Plus（第6版）中文版', null, '人民邮电出版社', ' C和C++实务精选', '9787115279460', '2012 年6月', '1-1', '2012-6-8', '合作专区微软技术图书 微软程序设计 CC++VC++', '99', '69', '69', '[全场]客户端首单立减5元!满48元免邮(仅限普通快递及平邮)', '644');
INSERT INTO `book` VALUES ('22', 'Professional C++, Second Edition', ' [比]Marc Gregoire    [美]Nicholas A. Solter    Scott JKleper  ', 'C++高级编程(第2版)(精通C++语言最新版本：C++11', '侯普秀 郑思遥', '清华大学出版社', null, '9787302298977', '2012 年10月', '2-1', '2012-11-5', '计算机 软件与程序设计 C++ C++', '108', '81', '81', '[全场]客户端首单立减5元!满48元免邮(仅限普通快递及平邮)', '976');
INSERT INTO `book` VALUES ('23', null, '邱铁    周玉    张民垒  ', 'Linux环境下Qt4图形界面与MySQL编程(深入剖析Linux GUI编程与MySQL设计实例)', ' 邱铁    周玉    张民垒  ', '机械工业出版社', '原创精品系列', '9787111372912', '2012 年3月', '1-1', '2012-3-13', '计算机操作系统Linux', '79', '53.72', '53.72', '[全场]客户端首单立减5元!满48元免邮(仅限普通快递及平邮)', '213');

-- ----------------------------
-- Table structure for `booksimilarity`
-- ----------------------------
DROP TABLE IF EXISTS `booksimilarity`;
CREATE TABLE `booksimilarity` (
  `similarityId` int(11) NOT NULL AUTO_INCREMENT,
  `bookId1` int(11) DEFAULT NULL,
  `bookId2` int(11) DEFAULT NULL,
  `similarity` float DEFAULT NULL,
  PRIMARY KEY (`similarityId`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

-- ----------------------------
-- Records of booksimilarity
-- ----------------------------

-- ----------------------------
-- Table structure for `rating`
-- ----------------------------
DROP TABLE IF EXISTS `rating`;
CREATE TABLE `rating` (
  `ratingId` int(11) NOT NULL AUTO_INCREMENT,
  `userId` int(11) DEFAULT NULL,
  `bookId` int(11) DEFAULT NULL,
  `rating` float DEFAULT NULL,
  `timestamp` varchar(32) DEFAULT NULL,
  PRIMARY KEY (`ratingId`)
) ENGINE=InnoDB AUTO_INCREMENT=37 DEFAULT CHARSET=utf8;

-- ----------------------------
-- Records of rating
-- ----------------------------
INSERT INTO `rating` VALUES ('1', '1', '1', '4.5', null);
INSERT INTO `rating` VALUES ('2', '1', '2', '4', null);
INSERT INTO `rating` VALUES ('3', '2', '2', '4.5', null);
INSERT INTO `rating` VALUES ('4', '2', '3', '4', null);
INSERT INTO `rating` VALUES ('5', '3', '3', '4.2', null);
INSERT INTO `rating` VALUES ('6', '3', '4', '3.5', null);
INSERT INTO `rating` VALUES ('7', '4', '4', '3.7', null);
INSERT INTO `rating` VALUES ('8', '4', '5', '4.6', null);
INSERT INTO `rating` VALUES ('9', '5', '5', '4.1', null);
INSERT INTO `rating` VALUES ('10', '5', '6', '4.7', null);
INSERT INTO `rating` VALUES ('11', '6', '6', '4.1', null);
INSERT INTO `rating` VALUES ('12', '6', '6', '3.5', null);
INSERT INTO `rating` VALUES ('13', '6', '7', '3.99', null);
INSERT INTO `rating` VALUES ('14', '6', '8', '4', null);
INSERT INTO `rating` VALUES ('15', '6', '9', '4.4', null);
INSERT INTO `rating` VALUES ('16', '6', '10', '3.3', null);
INSERT INTO `rating` VALUES ('17', '20', '1', '4.5', '');
INSERT INTO `rating` VALUES ('18', '20', '2', '3.9', null);
INSERT INTO `rating` VALUES ('19', '20', '3', '4.8', null);
INSERT INTO `rating` VALUES ('20', '19', '4', '4.6', null);
INSERT INTO `rating` VALUES ('21', '19', '5', '4.7', null);
INSERT INTO `rating` VALUES ('22', '19', '6', '4.8', null);
INSERT INTO `rating` VALUES ('23', '21', '7', '4.6', null);
INSERT INTO `rating` VALUES ('24', '21', '8', '4.8', null);
INSERT INTO `rating` VALUES ('25', '21', '9', '4.88', null);
INSERT INTO `rating` VALUES ('26', '21', '1', '3.7', '2014-10-09 11:52:03');
INSERT INTO `rating` VALUES ('27', '21', '2', '2.7', '2014-10-09 11:52:03');
INSERT INTO `rating` VALUES ('28', '21', '2', '3.9', '2014-10-09 12:16:41');
INSERT INTO `rating` VALUES ('29', '21', '7', '3.7', '2014-10-09 12:16:41');
INSERT INTO `rating` VALUES ('30', '21', '9', '4.1', '2014-10-09 12:16:41');
INSERT INTO `rating` VALUES ('31', '21', '1', '3.9', '2014-10-09 14:32:20');
INSERT INTO `rating` VALUES ('32', '21', '1', '0.8', '2014-10-09 15:49:48');
INSERT INTO `rating` VALUES ('33', '21', '1', '2.3', '2014-10-09 15:52:55');
INSERT INTO `rating` VALUES ('34', '21', '9', '1.6', '2014-10-09 16:38:53');
INSERT INTO `rating` VALUES ('35', '21', '8', '1.6', '2014-10-10 16:25:48');
INSERT INTO `rating` VALUES ('36', '21', '19', '3', '2014-10-10 16:26:02');

-- ----------------------------
-- Table structure for `user`
-- ----------------------------
DROP TABLE IF EXISTS `user`;
CREATE TABLE `user` (
  `userId` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(32) DEFAULT NULL,
  `usrpwd` varchar(128) DEFAULT NULL,
  `email` varchar(32) DEFAULT NULL,
  `status` varchar(32) DEFAULT NULL,
  `admirefield` varchar(32) DEFAULT NULL,
  `expertat` varchar(32) DEFAULT NULL,
  `tag` varchar(32) DEFAULT NULL,
  `knowfrom` varchar(32) DEFAULT NULL,
  PRIMARY KEY (`userId`)
) ENGINE=InnoDB AUTO_INCREMENT=22 DEFAULT CHARSET=utf8;

-- ----------------------------
-- Records of user
-- ----------------------------
INSERT INTO `user` VALUES ('1', 'matrix', 'matrix', 'matrix@matrix.com', '学生', '文学', '小说', '都市武侠', '搜索');
INSERT INTO `user` VALUES ('2', 'karry', 'karry', 'karry@karry.com', '老师', '经济管理', '经济学、马哲', '经济、政策', null);
INSERT INTO `user` VALUES ('3', 'fred', 'fred', 'fred@fred.com', '上班族', '编程C++', 'C、C++', '资深码农', null);
INSERT INTO `user` VALUES ('4', 'free', 'free', 'free@free.com', '自由职业', '网游、网络', '网游', 'soho、bytecoin', null);
INSERT INTO `user` VALUES ('5', 'master', 'master', 'master@master.com', '其他职业', '经营书店', '经营、审计', '经营、NBA', null);
INSERT INTO `user` VALUES ('6', 'nexus', 'nexus', 'nexus@nexus.com', '上班族', 'Ｃ++、Java', 'Java', '一线码农', null);
INSERT INTO `user` VALUES ('19', 'bbbb', '4124BC0A9335C27F086F24BA207A4912', 'aa@sina.com', '其他职业', '经济管理,历史,', '外语,文学,物理,小说,', '打散', '搜索引擎');
INSERT INTO `user` VALUES ('20', 'aaaa', '4124BC0A9335C27F086F24BA207A4912', 'aa@qq.com', '上班族', '经济管理,历史,', '外语,文学,物理,小说,', '打散', '搜索引擎');
INSERT INTO `user` VALUES ('21', 'cccc', 'E0323A9039ADD2978BF5B49550572C7C', 'cc@cc.com', '其他职业', '历史,数学,', '外语,文学,物理,', '打散', '朋友推荐');

-- ----------------------------
-- Table structure for `usersimilarity`
-- ----------------------------
DROP TABLE IF EXISTS `usersimilarity`;
CREATE TABLE `usersimilarity` (
  `usimilarityID` int(11) NOT NULL AUTO_INCREMENT,
  `userId1` int(11) DEFAULT NULL,
  `userId2` int(11) DEFAULT NULL,
  `usimilarity` float DEFAULT NULL,
  PRIMARY KEY (`usimilarityID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

-- ----------------------------
-- Records of usersimilarity
-- ----------------------------

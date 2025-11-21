import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_database/firebase_database.dart';
import 'package:intl/intl.dart' hide TextDirection;

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp();
  runApp(const YemenSarrafApp());
}

class YemenSarrafApp extends StatelessWidget {
  const YemenSarrafApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'صراف اليمن',
      theme: ThemeData(
        primarySwatch: Colors.teal,
        useMaterial3: true,
        fontFamily: 'Segoe UI',
        scaffoldBackgroundColor: const Color(0xFFF5F5F5),
      ),
      builder: (context, child) {
        return Directionality(
          textDirection: TextDirection.rtl,
          child: child!,
        );
      },
      home: const HomePage(),
    );
  }
}

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage>
    with SingleTickerProviderStateMixin {
  final DatabaseReference _dbRef = FirebaseDatabase.instance.ref();
  late TabController _tabController;
  final numberFormat = NumberFormat("#,##0", "en_US");

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
  }

  @override
  Widget build(BuildContext context) {
    return StreamBuilder(
      stream: _dbRef.onValue,
      builder: (context, AsyncSnapshot<DatabaseEvent> snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Scaffold(
              body: Center(child: CircularProgressIndicator()));
        }

        if (snapshot.hasError ||
            !snapshot.hasData ||
            snapshot.data!.snapshot.value == null) {
          return const Scaffold(
              body: Center(child: Text('جاري انتظار البيانات...')));
        }

        final data = snapshot.data!.snapshot.value as Map<dynamic, dynamic>;

        // نتأكد أن البيانات ليست فارغة لتجنب الأخطاء
        final rates = data['rates'] ?? {};
        final gold = data['gold'] ?? {};

        return Scaffold(
          appBar: AppBar(
            title: const Text('صراف اليمن 🇾🇪',
                style: TextStyle(
                    color: Colors.white, fontWeight: FontWeight.bold)),
            centerTitle: true,
            backgroundColor: Colors.teal[800],
            bottom: TabBar(
              controller: _tabController,
              labelColor: Colors.white,
              unselectedLabelColor: Colors.white54,
              indicatorColor: Colors.amber,
              tabs: const [
                Tab(icon: Icon(Icons.currency_exchange), text: 'العملات'),
                Tab(icon: Icon(Icons.monetization_on), text: 'الذهب'),
              ],
            ),
          ),

          // 👇 نمرر كامل البيانات للحاسبة لكي تختار منها (صنعاء أو عدن)
          floatingActionButton: FloatingActionButton.extended(
            onPressed: () => _showZakatCalculator(context, rates, gold),
            label: const Text('حاسبة الزكاة',
                style: TextStyle(fontWeight: FontWeight.bold)),
            icon: const Icon(Icons.calculate),
            backgroundColor: Colors.teal[900],
            foregroundColor: Colors.white,
          ),

          body: Column(
            children: [
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(8),
                color: Colors.amber[100],
                child: Text(
                  '⏰ آخر تحديث: ${rates['last_update'] ?? '...'}',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                      color: Colors.orange[900], fontWeight: FontWeight.bold),
                ),
              ),
              Expanded(
                child: TabBarView(
                  controller: _tabController,
                  children: [
                    ListView(
                      padding: const EdgeInsets.all(16),
                      children: [
                        _buildCitySection(
                            'صنعاء 🏛️', Colors.teal, rates['sanaa']),
                        const SizedBox(height: 20),
                        _buildCitySection('عدن 🌊', Colors.blue, rates['aden']),
                        const SizedBox(height: 80),
                      ],
                    ),
                    ListView(
                      padding: const EdgeInsets.all(16),
                      children: [
                        // عرض الذهب العالمي
                        _buildGoldCard(
                            'الأونصة عالمياً 🌍',
                            '\$${gold['global_ounce_usd'] ?? 0}',
                            Colors.purple),
                        const Divider(),
                        _buildGoldSection(
                            'أسعار الذهب - صنعاء', Colors.teal, gold['sanaa']),
                        const SizedBox(height: 20),
                        _buildGoldSection(
                            'أسعار الذهب - عدن', Colors.blue, gold['aden']),

                        const Padding(
                          padding: EdgeInsets.all(8.0),
                          child: Text('* الأسعار لا تشمل المصنعية',
                              style: TextStyle(color: Colors.grey),
                              textAlign: TextAlign.center),
                        ),
                        const SizedBox(height: 80),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  // --- 🧮 حاسبة الزكاة الذكية (مع اختيار المنطقة) ---
  void _showZakatCalculator(BuildContext context, Map rates, Map gold) {
    final yerController = TextEditingController();
    final usdController = TextEditingController();
    final sarController = TextEditingController();
    final goldGramsController = TextEditingController();

    // المتغير الافتراضي للمنطقة
    String selectedRegion = 'sanaa';
    String resultText = "";

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (context) {
        return StatefulBuilder(// ضروري لتحديث الواجهة عند تغيير المنطقة
            builder: (context, setState) {
          // 1. استخراج الأسعار بناءً على المنطقة المختارة حالياً
          final regionRates = rates[selectedRegion] ?? {};
          final regionGold = gold[selectedRegion] ?? {};

          final double usdRate = (regionRates['usd_buy'] ?? 0).toDouble();
          final double sarRate = (regionRates['sar_buy'] ?? 0).toDouble();
          final double gold24 = (regionGold['gram_24'] ?? 0).toDouble();
          final double gold21 = (regionGold['gram_21'] ?? 0).toDouble();

          // حساب النصاب (85 جرام عيار 24)
          final double nisabValue = gold24 * 85;

          return Padding(
            padding: EdgeInsets.only(
                bottom: MediaQuery.of(context).viewInsets.bottom,
                top: 20,
                left: 20,
                right: 20),
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Text("🕌 حاسبة الزكاة الشاملة",
                      style: TextStyle(
                          fontSize: 22,
                          fontWeight: FontWeight.bold,
                          color: Colors.teal)),
                  const SizedBox(height: 15),

                  // === أزرار تبديل المنطقة ===
                  Container(
                    decoration: BoxDecoration(
                        color: Colors.grey[200],
                        borderRadius: BorderRadius.circular(25)),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        // زر صنعاء
                        GestureDetector(
                          onTap: () => setState(() => selectedRegion = 'sanaa'),
                          child: Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 20, vertical: 10),
                            decoration: BoxDecoration(
                              color: selectedRegion == 'sanaa'
                                  ? Colors.teal
                                  : Colors.transparent,
                              borderRadius: BorderRadius.circular(25),
                            ),
                            child: Text('أسعار صنعاء 🏛️',
                                style: TextStyle(
                                    color: selectedRegion == 'sanaa'
                                        ? Colors.white
                                        : Colors.black54,
                                    fontWeight: FontWeight.bold)),
                          ),
                        ),
                        // زر عدن
                        GestureDetector(
                          onTap: () => setState(() => selectedRegion = 'aden'),
                          child: Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 20, vertical: 10),
                            decoration: BoxDecoration(
                              color: selectedRegion == 'aden'
                                  ? Colors.blue
                                  : Colors.transparent,
                              borderRadius: BorderRadius.circular(25),
                            ),
                            child: Text('أسعار عدن 🌊',
                                style: TextStyle(
                                    color: selectedRegion == 'aden'
                                        ? Colors.white
                                        : Colors.black54,
                                    fontWeight: FontWeight.bold)),
                          ),
                        ),
                      ],
                    ),
                  ),

                  const SizedBox(height: 15),

                  // شريط المعلومات الديناميكي
                  Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                        color: Colors.amber[50],
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: Colors.amber)),
                    child: Column(
                      children: [
                        Text(
                            "نصاب الزكاة (${selectedRegion == 'sanaa' ? 'صنعاء' : 'عدن'}):",
                            style: TextStyle(
                                fontSize: 12, color: Colors.orange[900])),
                        Text("${numberFormat.format(nisabValue)} ريال",
                            style: TextStyle(
                                fontSize: 16,
                                fontWeight: FontWeight.bold,
                                color: Colors.orange[900])),
                        const SizedBox(height: 5),
                        Text(
                            "(يتم التحويل بسعر صرف: \$1 = ${numberFormat.format(usdRate)})",
                            style: TextStyle(
                                fontSize: 10, color: Colors.grey[600])),
                      ],
                    ),
                  ),

                  const SizedBox(height: 20),

                  _buildInput(
                      yerController, "نقد بالريال اليمني", Icons.money, null),
                  const SizedBox(height: 10),

                  Row(
                    children: [
                      Expanded(
                          child: _buildInput(usdController, "دولار (\$)",
                              Icons.attach_money, Colors.green)),
                      const SizedBox(width: 10),
                      Expanded(
                          child: _buildInput(sarController, "سعودي (SAR)",
                              Icons.currency_exchange, Colors.teal)),
                    ],
                  ),
                  const SizedBox(height: 10),
                  _buildInput(goldGramsController, "ذهب (جرام عيار 21)",
                      Icons.monitor_weight, Colors.amber[700]),

                  const SizedBox(height: 20),

                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton(
                      style: ElevatedButton.styleFrom(
                          backgroundColor: selectedRegion == 'sanaa'
                              ? Colors.teal[800]
                              : Colors.blue[800],
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(vertical: 12)),
                      onPressed: () {
                        double yer = double.tryParse(yerController.text) ?? 0;
                        double usd = double.tryParse(usdController.text) ?? 0;
                        double sar = double.tryParse(sarController.text) ?? 0;
                        double grams =
                            double.tryParse(goldGramsController.text) ?? 0;

                        // المعادلة الشاملة
                        double totalWealthYER = yer +
                            (usd * usdRate) +
                            (sar * sarRate) +
                            (grams * gold21);

                        if (totalWealthYER >= nisabValue) {
                          double zakatAmount = totalWealthYER * 0.025;
                          setState(() {
                            resultText = "✅ تجب عليك الزكاة!\n"
                                "إجمالي الثروة: ${numberFormat.format(totalWealthYER)} ريال\n"
                                "----------------\n"
                                "الواجب إخراجه: ${numberFormat.format(zakatAmount)} ريال";
                          });
                        } else {
                          setState(() {
                            resultText =
                                "✋ لا تجب عليك الزكاة.\nإجمالي ثروتك (${numberFormat.format(totalWealthYER)}) لم تبلغ النصاب.";
                          });
                        }
                      },
                      child: const Text("احسب الزكاة",
                          style: TextStyle(fontSize: 18)),
                    ),
                  ),
                  const SizedBox(height: 20),
                  if (resultText.isNotEmpty)
                    Container(
                      padding: const EdgeInsets.all(15),
                      width: double.infinity,
                      decoration: BoxDecoration(
                          color: resultText.contains("✅")
                              ? Colors.green[50]
                              : Colors.red[50],
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(
                              color: resultText.contains("✅")
                                  ? Colors.green
                                  : Colors.red)),
                      child: Text(
                        resultText,
                        textAlign: TextAlign.center,
                        style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.bold,
                            height: 1.5,
                            color: resultText.contains("✅")
                                ? Colors.green[800]
                                : Colors.red[800]),
                      ),
                    ),
                  const SizedBox(height: 20),
                ],
              ),
            ),
          );
        });
      },
    );
  }

  // ✅ هذه هي الدالة التي سألت عنها - يجب أن تبقى موجودة!
  Widget _buildInput(TextEditingController controller, String label,
      IconData icon, Color? iconColor) {
    return TextField(
      controller: controller,
      keyboardType: TextInputType.number,
      decoration: InputDecoration(
        labelText: label,
        isDense: true,
        border: const OutlineInputBorder(),
        prefixIcon: Icon(icon, color: iconColor ?? Colors.grey),
      ),
    );
  }

  // --- بقية دوال التصميم ---
  Widget _buildCitySection(String title, MaterialColor color, Map? data) {
    if (data == null) return const SizedBox();
    return Column(
      children: [
        Text(title,
            style: TextStyle(
                fontSize: 20, fontWeight: FontWeight.bold, color: color[800])),
        const SizedBox(height: 10),
        _buildRateCard(
            '🇺🇸 الدولار الأمريكي', data['usd_buy'], data['usd_sell'], color),
        _buildRateCard(
            '🇸🇦 الريال السعودي', data['sar_buy'], data['sar_sell'], color),
      ],
    );
  }

  Widget _buildRateCard(
      String currency, var buy, var sell, MaterialColor color) {
    return Card(
      elevation: 3,
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            Text(currency,
                style:
                    const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
            const Divider(),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceAround,
              children: [
                _buildPriceColumn('شراء', '$buy', color[700]!),
                Container(height: 30, width: 1, color: Colors.grey[300]),
                _buildPriceColumn('بيع', '$sell', Colors.red[400]!),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildPriceColumn(String label, String price, Color color) {
    return Column(
      children: [
        Text(label, style: TextStyle(color: Colors.grey[600], fontSize: 12)),
        Text(numberFormat.format(int.tryParse(price) ?? 0),
            style: TextStyle(
                fontSize: 20, fontWeight: FontWeight.bold, color: color)),
      ],
    );
  }

  Widget _buildGoldSection(String title, MaterialColor color, Map? data) {
    if (data == null) return const SizedBox();
    return Column(
      children: [
        Text(title,
            style: TextStyle(
                fontSize: 18, fontWeight: FontWeight.bold, color: color[800])),
        const SizedBox(height: 10),
        _buildGoldCard('جرام 21 (زينة)', data['gram_21'], Colors.amber),
        _buildGoldCard('الجنيه الذهب', data['gunaih'], Colors.amber),
      ],
    );
  }

  Widget _buildGoldCard(String title, var price, MaterialColor color) {
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: CircleAvatar(
            backgroundColor: color[100],
            child: Icon(Icons.lens, color: color[700], size: 15)),
        title: Text(title, style: const TextStyle(fontWeight: FontWeight.bold)),
        trailing: Text(
            '${numberFormat.format(price is int ? price : (double.tryParse(price.toString()) ?? 0))} ريال',
            style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
      ),
    );
  }
}

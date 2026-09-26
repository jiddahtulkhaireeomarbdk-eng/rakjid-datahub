import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

const String configuredBackendUrl = String.fromEnvironment('BACKEND_URL');
final String backendBaseUrl = configuredBackendUrl.isNotEmpty
  ? configuredBackendUrl
  : (kIsWeb ? 'http://127.0.0.1:5000' : 'http://10.0.2.2:5000');

Future<AppConfig> fetchAppConfig() async {
  final response = await http.get(Uri.parse('$backendBaseUrl/api/config'));
  if (response.statusCode != 200) {
    throw Exception('Failed to load app configuration');
  }
  return AppConfig.fromJson(jsonDecode(response.body));
}

Future<List<DataPlan>> fetchPlans() async {
  final response = await http.get(Uri.parse('$backendBaseUrl/api/plans'));
  if (response.statusCode != 200) {
    throw Exception('Failed to load data plans');
  }

  final payload = jsonDecode(response.body);
  final rawPlans = payload['plans'] as List? ?? const [];

  return rawPlans
      .map((plan) => DataPlan.fromJson(plan as Map<String, dynamic>))
      .toList();
}

Future<WalletState> fetchWallet() async {
  final headers = <String, String>{};
  final userId = currentUserId;
  if (userId != null && userId.isNotEmpty) {
    headers['X-User-Id'] = userId;
  }

  final response = await http.get(
    Uri.parse('$backendBaseUrl/api/wallet'),
    headers: headers,
  );
  if (response.statusCode != 200) {
    throw Exception('Failed to load wallet');
  }
  return WalletState.fromJson(jsonDecode(response.body));
}

Future<List<TransactionItem>> fetchTransactions() async {
  final headers = <String, String>{};
  final userId = currentUserId;
  if (userId != null && userId.isNotEmpty) {
    headers['X-User-Id'] = userId;
  }

  final response = await http.get(
    Uri.parse('$backendBaseUrl/api/transactions'),
    headers: headers,
  );
  if (response.statusCode != 200) {
    throw Exception('Failed to load transaction history');
  }

  final payload = jsonDecode(response.body);
  final raw = payload['transactions'] as List? ?? const [];

  return raw
      .map((value) => TransactionItem.fromJson(value as Map<String, dynamic>))
      .toList();
}

String? currentUserId;

class AppConfig {
  final String provider;
  final bool demoMode;
  final Map<String, int> networks;

  const AppConfig({
    required this.provider,
    required this.demoMode,
    required this.networks,
  });

  factory AppConfig.fromJson(Map<String, dynamic> json) {
    return AppConfig(
      provider: json['provider'] as String? ?? 'Unknown',
      demoMode: json['demoMode'] as bool? ?? false,
      networks: Map<String, int>.from(json['networks'] ?? const {}),
    );
  }
}

class WalletState {
  final double balance;
  final String currency;

  const WalletState({required this.balance, required this.currency});

  factory WalletState.fromJson(Map<String, dynamic> json) {
    return WalletState(
      balance: (json['balance'] as num?)?.toDouble() ?? 0.0,
      currency: json['currency'] as String? ?? 'NGN',
    );
  }

  String get displayBalance => '₦${balance.toStringAsFixed(2)}';
}

class AuthUser {
  final String id;
  final String name;
  final String email;
  final double walletBalance;

  const AuthUser({
    required this.id,
    required this.name,
    required this.email,
    required this.walletBalance,
  });

  factory AuthUser.fromJson(Map<String, dynamic> json) {
    return AuthUser(
      id: json['id']?.toString() ?? '',
      name: json['name']?.toString() ?? 'User',
      email: json['email']?.toString() ?? '',
      walletBalance: (json['wallet_balance'] as num?)?.toDouble() ?? 0.0,
    );
  }
}

Future<AuthUser> loginUser(String email, String password) async {
  final response = await http.post(
    Uri.parse('$backendBaseUrl/api/auth/login'),
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode({'email': email.trim(), 'password': password}),
  );

  final payload = jsonDecode(response.body);
  if (response.statusCode != 200 || payload['success'] != true) {
    throw Exception(payload['message'] ?? 'Login failed');
  }

  final user = AuthUser.fromJson(payload['user'] as Map<String, dynamic>);
  currentUserId = user.id;
  return user;
}

Future<AuthUser> signupUser(String name, String email, String password) async {
  final response = await http.post(
    Uri.parse('$backendBaseUrl/api/auth/signup'),
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode({
      'name': name.trim(),
      'email': email.trim(),
      'password': password,
    }),
  );

  final payload = jsonDecode(response.body);
  if (response.statusCode != 201 || payload['success'] != true) {
    throw Exception(payload['message'] ?? 'Account creation failed');
  }

  final user = AuthUser.fromJson(payload['user'] as Map<String, dynamic>);
  currentUserId = user.id;
  return user;
}

class DataPlan {
  final String id;
  final String network;
  final String name;
  final int amount;

  const DataPlan({
    required this.id,
    required this.network,
    required this.name,
    required this.amount,
  });

  factory DataPlan.fromJson(Map<String, dynamic> json) {
    return DataPlan(
      id: json['id']?.toString() ?? '',
      network: json['network']?.toString() ?? 'Unknown',
      name: json['plan']?.toString() ?? json['name']?.toString() ?? 'Data plan',
      amount: (json['amount'] is int)
          ? json['amount'] as int
          : int.tryParse(json['amount']?.toString() ?? '0') ?? 0,
    );
  }

  String get displayPrice => '₦${amount.toString()}';
}

class TransactionItem {
  final String id;
  final String title;
  final String type;
  final double amount;
  final String status;
  final String createdAt;

  const TransactionItem({
    required this.id,
    required this.title,
    required this.type,
    required this.amount,
    required this.status,
    required this.createdAt,
  });

  factory TransactionItem.fromJson(Map<String, dynamic> json) {
    return TransactionItem(
      id: json['id']?.toString() ?? '',
      title: json['title']?.toString() ?? 'Transaction',
      type: json['type']?.toString() ?? 'general',
      amount: (json['amount'] as num?)?.toDouble() ?? 0.0,
      status: json['status']?.toString() ?? 'pending',
      createdAt: json['created_at']?.toString() ?? '',
    );
  }

  String get displayAmount => '₦${amount.toStringAsFixed(2)}';
}

void main() {
  runApp(const RakjidDataHubApp());
}

class RakjidDataHubApp extends StatelessWidget {
  const RakjidDataHubApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'RAKJID DataHub',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF14A34A)),
        scaffoldBackgroundColor: const Color(0xFFF5FBF7),
        fontFamily: 'Roboto',
        useMaterial3: true,
        appBarTheme: const AppBarTheme(
          backgroundColor: Color(0xFF0B8B45),
          foregroundColor: Colors.white,
        ),
      ),
      home: const AuthScreen(),
    );
  }
}

class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key});

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  final _nameController = TextEditingController();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _isLogin = true;
  bool _isLoading = false;

  Future<void> _submit() async {
    final name = _nameController.text.trim();
    final email = _emailController.text.trim();
    final password = _passwordController.text;

    if (email.isEmpty || password.isEmpty || (!_isLogin && name.isEmpty)) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Please fill in all required fields')),
      );
      return;
    }

    setState(() => _isLoading = true);

    try {
      final user = _isLogin
          ? await loginUser(email, password)
          : await signupUser(name, email, password);

      if (!mounted) return;

      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => AppShell(user: user)),
      );
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(error.toString())),
        );
      }
    } finally {
      if (mounted) {
        setState(() => _isLoading = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Container(
              constraints: const BoxConstraints(maxWidth: 420),
              padding: const EdgeInsets.all(24),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(30),
                boxShadow: [
                  BoxShadow(
                    color: const Color(0xFF0B8B45).withAlpha((255 * 0.12).round()),
                    blurRadius: 20,
                    offset: const Offset(0, 12),
                  ),
                ],
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: 64,
                    height: 64,
                    decoration: BoxDecoration(
                      color: const Color(0xFF0E9F5A),
                      borderRadius: BorderRadius.circular(18),
                    ),
                    child: const Icon(Icons.account_balance_wallet, color: Colors.white, size: 30),
                  ),
                  const SizedBox(height: 18),
                  const Text(
                    'Welcome to RAKJID DataHub',
                    style: TextStyle(fontSize: 28, fontWeight: FontWeight.w800),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    _isLogin ? 'Sign in to continue' : 'Create your account',
                    style: const TextStyle(color: Colors.black54, fontSize: 15),
                  ),
                  const SizedBox(height: 24),
                  Row(
                    children: [
                      Expanded(
                        child: ChoiceChip(
                          label: const Text('Login'),
                          selected: _isLogin,
                          onSelected: (_) => setState(() => _isLogin = true),
                          selectedColor: const Color(0xFF0E9F5A),
                          labelStyle: TextStyle(
                            color: _isLogin ? Colors.white : Colors.black87,
                          ),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: ChoiceChip(
                          label: const Text('Create account'),
                          selected: !_isLogin,
                          onSelected: (_) => setState(() => _isLogin = false),
                          selectedColor: const Color(0xFF0E9F5A),
                          labelStyle: TextStyle(
                            color: !_isLogin ? Colors.white : Colors.black87,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 24),
                  if (!_isLogin)
                    TextField(
                      controller: _nameController,
                      decoration: const InputDecoration(
                        labelText: 'Full name',
                        border: OutlineInputBorder(),
                      ),
                    ),
                  if (!_isLogin) const SizedBox(height: 16),
                  TextField(
                    controller: _emailController,
                    keyboardType: TextInputType.emailAddress,
                    decoration: const InputDecoration(
                      labelText: 'Email address',
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 16),
                  TextField(
                    controller: _passwordController,
                    obscureText: true,
                    decoration: const InputDecoration(
                      labelText: 'Password',
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 24),
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton(
                      onPressed: _isLoading ? null : _submit,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFF0E9F5A),
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 16),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(14),
                        ),
                      ),
                      child: _isLoading
                          ? const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                            )
                          : Text(_isLogin ? 'Login' : 'Create account'),
                    ),
                  ),
                  const SizedBox(height: 18),
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: const Color(0xFFF3FBF6),
                      borderRadius: BorderRadius.circular(14),
                    ),
                    child: const Text(
                      'Demo mode: use any valid email and password to create or sign in.',
                      style: TextStyle(color: Color(0xFF0E9F5A), fontSize: 12),
                    ),
                  )
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class AppShell extends StatefulWidget {
  final AuthUser? user;

  const AppShell({super.key, this.user});

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  int _selectedIndex = 0;
  final ValueNotifier<double> _walletBalance = ValueNotifier<double>(0);

  void _openPage(int index) {
    setState(() => _selectedIndex = index);
  }

  @override
  Widget build(BuildContext context) {
    final pages = <Widget>[
      DashboardTab(
        walletBalance: _walletBalance,
        onActionTap: _openPage,
        user: widget.user,
      ),
      TopupTab(walletBalance: _walletBalance),
      AirtimeTab(),
      HistoryTab(),
    ];

    return Scaffold(
      appBar: AppBar(
        toolbarHeight: 90,
        backgroundColor: const Color(0xFFF5FBF7),
        elevation: 0,
        title: Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Good morning',
                style: const TextStyle(
                  fontSize: 12,
                  color: Colors.black54,
                  fontWeight: FontWeight.w500,
                ),
              ),
              const SizedBox(height: 3),
              Text(
                widget.user?.name ?? 'RAKJID DataHub',
                style: const TextStyle(
                  fontSize: 24,
                  fontWeight: FontWeight.w700,
                  color: Color(0xFF0B8B45),
                ),
              ),
            ],
          ),
        ),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 16, top: 8),
            child: PopupMenuButton<String>(
              onSelected: (value) {
                if (value == 'logout') {
                  Navigator.of(context).pushAndRemoveUntil(
                    MaterialPageRoute(builder: (_) => const AuthScreen()),
                    (route) => false,
                  );
                }
              },
              itemBuilder: (context) => const [
                PopupMenuItem(value: 'logout', child: Text('Log out')),
              ],
              child: const CircleAvatar(
                radius: 18,
                backgroundColor: Color(0xFF0B8B45),
                child: Icon(Icons.person, color: Colors.white, size: 20),
              ),
            ),
          ),
        ],
      ),
      body: IndexedStack(
        index: _selectedIndex,
        children: pages,
      ),
      bottomNavigationBar: NavigationBar(
        backgroundColor: Colors.white,
        elevation: 8,
        selectedIndex: _selectedIndex,
        onDestinationSelected: (index) => setState(() => _selectedIndex = index),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home), label: 'Home'),
          NavigationDestination(icon: Icon(Icons.account_balance_wallet), label: 'Wallet'),
          NavigationDestination(icon: Icon(Icons.phone_android), label: 'Airtime'),
          NavigationDestination(icon: Icon(Icons.receipt_long), label: 'History'),
        ],
      ),
    );
  }
}

class DashboardTab extends StatefulWidget {
  final ValueNotifier<double> walletBalance;
  final void Function(int index)? onActionTap;
  final AuthUser? user;

  const DashboardTab({
    super.key,
    required this.walletBalance,
    this.onActionTap,
    this.user,
  });

  @override
  State<DashboardTab> createState() => _DashboardTabState();
}

class _DashboardTabState extends State<DashboardTab> {
  late final Future<Map<String, dynamic>> _homeData;

  @override
  void initState() {
    super.initState();
    _homeData = Future.wait([
      fetchAppConfig(),
      fetchPlans(),
      fetchWallet(),
    ]).then((results) {
      final wallet = results[2] as WalletState;
      widget.walletBalance.value = wallet.balance;
      return {
        'config': results[0] as AppConfig,
        'plans': results[1] as List<DataPlan>,
        'wallet': wallet,
      };
    });
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Map<String, dynamic>>(
      future: _homeData,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Center(child: CircularProgressIndicator());
        }

        if (snapshot.hasError) {
          return Center(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Text(snapshot.error.toString()),
            ),
          );
        }

        final config = snapshot.data!['config'] as AppConfig;
        final plans = snapshot.data!['plans'] as List<DataPlan>;

        return ValueListenableBuilder<double>(
          valueListenable: widget.walletBalance,
          builder: (context, balance, _) {
            final currentBalance = balance > 0 ? balance : (snapshot.data!['wallet'] as WalletState).balance;

            return ListView(
              padding: const EdgeInsets.all(20),
              children: [
                Container(
                  padding: const EdgeInsets.all(22),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(28),
                    gradient: const LinearGradient(
                      colors: [Color(0xFF0E9F5A), Color(0xFF27C77D)],
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ),
                    boxShadow: [
                      BoxShadow(
                        color: const Color(0xFF14A34A).withAlpha((255 * 0.30).round()),
                        blurRadius: 18,
                        offset: const Offset(0, 8),
                      ),
                    ],
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(
                            widget.user != null ? 'Welcome, ${widget.user!.name}' : 'Wallet balance',
                            style: const TextStyle(color: Colors.white70, fontSize: 15),
                          ),
                          const Icon(Icons.visibility, color: Colors.white70),
                        ],
                      ),
                      const SizedBox(height: 18),
                      Text(
                        '₦${currentBalance.toStringAsFixed(2)}',
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 34,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      const SizedBox(height: 18),
                      Row(
                        children: [
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                            decoration: BoxDecoration(
                              color: Colors.white.withAlpha((255 * 0.16).round()),
                              borderRadius: BorderRadius.circular(20),
                            ),
                            child: const Text(
                              'Provider: SME API',
                              style: TextStyle(color: Colors.white70, fontSize: 12),
                            ),
                          ),
                        ],
                      )
                    ],
                  ),
                ),
                const SizedBox(height: 20),
                Container(
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(22),
                    border: Border.all(color: const Color(0xFFE6F2EA)),
                    boxShadow: [
                      BoxShadow(
                        color: const Color(0xFF0B8B45).withAlpha((255 * 0.08).round()),
                        blurRadius: 12,
                        offset: const Offset(0, 5),
                      ),
                    ],
                  ),
                  child: const Text(
                    'Quick actions',
                    style: TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w700,
                      color: Color(0xFF123028),
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    _ActionPill(
                      icon: Icons.add,
                      label: 'Fund Wallet',
                      onTap: () => widget.onActionTap?.call(1),
                    ),
                    const SizedBox(width: 12),
                    _ActionPill(
                      icon: Icons.smartphone,
                      label: 'Airtime',
                      onTap: () => widget.onActionTap?.call(2),
                    ),
                  ],
                ),
                const SizedBox(height: 20),
                const Text(
                  'Available networks',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: config.networks.entries
                      .map((entry) => Container(
                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                            decoration: BoxDecoration(
                              color: Colors.white,
                              borderRadius: BorderRadius.circular(16),
                              border: Border.all(color: const Color(0xFFE6E8F5)),
                            ),
                            child: Text(entry.key),
                          ))
                      .toList(),
                ),
                const SizedBox(height: 22),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: const [
                    Text(
                      'Data plans',
                      style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                    ),
                    Text(
                      'See all',
                      style: TextStyle(
                        color: Color(0xFF0B8B45),
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                ...plans.map(
                  (plan) => Container(
                    margin: const EdgeInsets.only(bottom: 12),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(color: const Color(0xFFEDEFFF)),
                    ),
                    child: ListTile(
                      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                      title: Text(
                        '${plan.network} • ${plan.name}',
                        style: const TextStyle(fontWeight: FontWeight.w600),
                      ),
                      subtitle: Text('Plan ID: ${plan.id}'),
                      trailing: Text(
                        plan.displayPrice,
                        style: const TextStyle(
                          fontWeight: FontWeight.bold,
                          fontSize: 16,
                          color: Color(0xFF0E9F5A),
                        ),
                      ),
                      onTap: () => Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) => PurchaseScreen(plan: plan),
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            );
          },
        );
      },
    );
  }
}

class _ActionPill extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  const _ActionPill({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: GestureDetector(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 14),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(18),
            border: Border.all(color: const Color(0xFFE6F2EA)),
            boxShadow: [
              BoxShadow(
                color: const Color(0xFF0B8B45).withAlpha((255 * 0.05).round()),
                blurRadius: 10,
                offset: const Offset(0, 4),
              ),
            ],
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icon, color: const Color(0xFF0B8B45), size: 18),
              const SizedBox(width: 8),
              Text(
                label,
                style: const TextStyle(
                  fontWeight: FontWeight.w600,
                  color: Color(0xFF1B1B2F),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class AirtimeTab extends StatefulWidget {
  const AirtimeTab({super.key});

  @override
  State<AirtimeTab> createState() => _AirtimeTabState();
}

class _AirtimeTabState extends State<AirtimeTab> {
  final TextEditingController _phoneController = TextEditingController();
  final TextEditingController _amountController = TextEditingController();
  String _network = 'MTN';
  bool _isSubmitting = false;

  Future<void> _submit() async {
    final phone = _phoneController.text.trim();
    final amountText = _amountController.text.trim();
    final amount = double.tryParse(amountText) ?? 0;

    if (phone.isEmpty || amount <= 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Enter a valid phone number and amount')),
      );
      return;
    }

    setState(() => _isSubmitting = true);

    try {
      final response = await http.post(
        Uri.parse('$backendBaseUrl/api/airtime'),
        headers: {
          'Content-Type': 'application/json',
          if (currentUserId != null && currentUserId!.isNotEmpty) 'X-User-Id': currentUserId!,
        },
        body: jsonEncode({
          'phone': phone,
          'network': _network,
          'amount': amount,
        }),
      );

      final payload = jsonDecode(response.body);
      if (response.statusCode != 200 || payload['success'] != true) {
        throw Exception(payload['message'] ?? 'Airtime purchase failed');
      }

      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Airtime purchase queued successfully')),
      );
      _phoneController.clear();
      _amountController.clear();
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(error.toString())),
        );
      }
    } finally {
      if (mounted) {
        setState(() => _isSubmitting = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Buy Airtime',
            style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 20),
          DropdownButtonFormField<String>(
            initialValue: _network,
            decoration: const InputDecoration(
              labelText: 'Network',
              border: OutlineInputBorder(),
            ),
            items: const [
              DropdownMenuItem(value: 'MTN', child: Text('MTN')),
              DropdownMenuItem(value: 'Airtel', child: Text('Airtel')),
              DropdownMenuItem(value: 'Glo', child: Text('Glo')),
              DropdownMenuItem(value: '9mobile', child: Text('9mobile')),
            ],
            onChanged: (value) => setState(() => _network = value ?? 'MTN'),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _phoneController,
            keyboardType: TextInputType.phone,
            decoration: const InputDecoration(
              labelText: 'Phone number',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _amountController,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(
              labelText: 'Amount',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 24),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              onPressed: _isSubmitting ? null : _submit,
              child: _isSubmitting
                  ? const CircularProgressIndicator()
                  : const Text('Buy Airtime'),
            ),
          ),
        ],
      ),
    );
  }
}

class TopupTab extends StatefulWidget {
  final ValueNotifier<double> walletBalance;

  const TopupTab({super.key, required this.walletBalance});

  @override
  State<TopupTab> createState() => _TopupTabState();
}

class _TopupTabState extends State<TopupTab> {
  final TextEditingController _amountController = TextEditingController();
  bool _isSubmitting = false;

  Future<void> _submit() async {
    final amountText = _amountController.text.trim();
    final amount = double.tryParse(amountText) ?? 0;

    if (amount <= 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Enter a valid top-up amount')),
      );
      return;
    }

    setState(() => _isSubmitting = true);

    try {
      final response = await http.post(
        Uri.parse('$backendBaseUrl/api/wallet/topup'),
        headers: {
          'Content-Type': 'application/json',
          if (currentUserId != null && currentUserId!.isNotEmpty) 'X-User-Id': currentUserId!,
        },
        body: jsonEncode({'amount': amount}),
      );

      final payload = jsonDecode(response.body);
      if (response.statusCode != 200 || payload['success'] != true) {
        throw Exception(payload['message'] ?? 'Top-up failed');
      }

      if (!mounted) return;
      widget.walletBalance.value += amount;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Wallet top-up successful')),
      );
      _amountController.clear();
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(error.toString())),
        );
      }
    } finally {
      if (mounted) setState(() => _isSubmitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Fund Wallet',
            style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 18),
          TextField(
            controller: _amountController,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(
              labelText: 'Top-up amount (NGN)',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 24),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              onPressed: _isSubmitting ? null : _submit,
              child: _isSubmitting
                  ? const CircularProgressIndicator()
                  : const Text('Top Up Wallet'),
            ),
          ),
        ],
      ),
    );
  }
}

class HistoryTab extends StatefulWidget {
  const HistoryTab({super.key});

  @override
  State<HistoryTab> createState() => _HistoryTabState();
}

class _HistoryTabState extends State<HistoryTab> {
  late final Future<List<TransactionItem>> _history;

  @override
  void initState() {
    super.initState();
    _history = fetchTransactions();
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<TransactionItem>>(
      future: _history,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Center(child: CircularProgressIndicator());
        }

        if (snapshot.hasError) {
          return Center(child: Text(snapshot.error.toString()));
        }

        final transactions = snapshot.data ?? const <TransactionItem>[];

        if (transactions.isEmpty) {
          return const Center(child: Text('No transactions yet'));
        }

        return ListView.separated(
          padding: const EdgeInsets.all(20),
          itemCount: transactions.length,
          separatorBuilder: (_, __) => const Divider(),
          itemBuilder: (context, index) {
            final transaction = transactions[index];
            return ListTile(
              title: Text(transaction.title),
              subtitle: Text(transaction.type),
              trailing: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    transaction.displayAmount,
                    style: const TextStyle(fontWeight: FontWeight.bold),
                  ),
                  Text(transaction.status),
                ],
              ),
            );
          },
        );
      },
    );
  }
}

class PurchaseScreen extends StatefulWidget {
  final DataPlan plan;

  const PurchaseScreen({super.key, required this.plan});

  @override
  State<PurchaseScreen> createState() => _PurchaseScreenState();
}

class _PurchaseScreenState extends State<PurchaseScreen> {
  final TextEditingController _phoneController = TextEditingController();
  bool _isSubmitting = false;

  Future<void> _purchase() async {
    final phone = _phoneController.text.trim();
    if (phone.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Enter a valid phone number')),
      );
      return;
    }

    setState(() => _isSubmitting = true);

    try {
      final response = await http.post(
        Uri.parse('$backendBaseUrl/api/purchase'),
        headers: {
          'Content-Type': 'application/json',
          if (currentUserId != null && currentUserId!.isNotEmpty) 'X-User-Id': currentUserId!,
        },
        body: jsonEncode({
          'plan_id': widget.plan.id,
          'phone': phone,
          'network': widget.plan.network,
        }),
      );

      final payload = jsonDecode(response.body);
      if (response.statusCode != 200 || payload['success'] != true) {
        throw Exception(payload['message'] ?? 'Purchase failed');
      }

      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'Purchase request created for ${widget.plan.network} ${widget.plan.name} on $phone',
          ),
        ),
      );
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(error.toString())),
        );
      }
    } finally {
      if (mounted) setState(() => _isSubmitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Buy Data')),
      body: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '${widget.plan.network} • ${widget.plan.name}',
              style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 12),
            Text(
              'Price: ${widget.plan.displayPrice}',
              style: const TextStyle(fontSize: 18),
            ),
            const SizedBox(height: 24),
            TextField(
              controller: _phoneController,
              keyboardType: TextInputType.phone,
              decoration: const InputDecoration(
                labelText: 'Phone number',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 24),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: _isSubmitting ? null : _purchase,
                child: _isSubmitting
                    ? const CircularProgressIndicator()
                    : const Text('Complete Purchase'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

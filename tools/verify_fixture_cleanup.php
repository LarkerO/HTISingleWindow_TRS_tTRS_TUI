<?php
declare(strict_types=1);
$backend = getenv('TTRS_BACKEND_DIR') ?: dirname(__DIR__, 2) . '/backend';
require $backend . '/vendor/autoload.php';
$app = new think\App($backend);
$app->initialize();
$suffix = $argv[1] ?? '';
if (!preg_match('/^[A-F0-9]{10}$/', $suffix)) {
    throw new RuntimeException('Invalid fixture suffix');
}
$counts = [
    'trips' => think\facade\Db::table('trips')->where('dimension', 'passenger-ui/' . $suffix)->count(),
    'tickets' => think\facade\Db::table('tickets')->where('agency_code', 'PA' . $suffix)->count(),
    'agencies' => think\facade\Db::table('agencies')->where('code', 'PA' . $suffix)->count(),
    'operators' => think\facade\Db::table('operators')->where('code', 'PD' . $suffix)->count(),
    'documents' => think\facade\Db::table('passenger_documents')
        ->where('document_type', 'PASSPORT')->where('issuing_country', 'CHN')
        ->whereIn('document_number', ['UI-' . $suffix, 'UI-' . $suffix . '-EXTRA'])->count(),
];
if (array_sum($counts) !== 0) {
    throw new RuntimeException('Fixture records remain: ' . json_encode($counts));
}
echo json_encode($counts);
